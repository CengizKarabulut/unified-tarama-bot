import json
import os
import asyncio
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from playwright.async_api import async_playwright
import logging
import sys

# BorsaPy Entegrasyonu
try:
    from borsapy import Borsa
    borsa_client = Borsa()
except ImportError:
    logging.warning("⚠️ BorsaPy bulunamadı. Sadece yfinance kullanılacak.")
    borsa_client = None

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
# YAPILANDIRMA (CONFIG)
# -----------------------------
STATE_FILE = "state.json"
TICKERS_FILE = "tickers.txt"
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TV_CHART_ID = os.getenv("TV_CHART_ID")

# -----------------------------
# DURUM YÖNETİMİ (STATE)
# -----------------------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_sent": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            if "last_sent" not in state: state["last_sent"] = {}
            return state
    except:
        return {"last_sent": {}}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"❌ State kaydedilemedi: {e}")

# -----------------------------
# TELEGRAM İLETİŞİM
# -----------------------------
def tg_send_message(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except: pass

def tg_send_photo(photo_path: str, caption: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
    except: pass

# -----------------------------
# TRADINGVIEW EKRAN GÖRÜNTÜSÜ
# -----------------------------
async def get_tv_screenshot(symbol, exchange, interval_str):
    tv_intervals = {"1H": "60", "4H": "240", "1D": "D", "1W": "W"}
    tv_interval = tv_intervals.get(interval_str, "D")
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{symbol}_{interval_str}.png"
    
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            page = await context.new_page()
            
            # Sembol formatı (BIST:THYAO gibi)
            chart_symbol = f"{exchange}:{symbol}"
            chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol={chart_symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol={chart_symbol}&interval={tv_interval}"
            
            await page.goto(chart_url, wait_until="networkidle")
            await asyncio.sleep(8) # Grafik çizimi için bekleme
            await page.screenshot(path=screenshot_path)
            return screenshot_path
        except Exception as e:
            logging.error(f"❌ Screenshot Hatası ({symbol}): {e}")
            return None
        finally:
            if browser: await browser.close()

# -----------------------------
# TEKNİK ANALİZ (SMI & MACD)
# -----------------------------
def ema(s, l): return s.ewm(span=l, adjust=False).mean()
def ema2(s, l): return ema(ema(s, l), l)

def calc_smi(df):
    hh = df["High"].rolling(10).max()
    ll = df["Low"].rolling(10).min()
    rng = (hh - ll).replace(0, 0.000001)
    rel = df["Close"] - (hh + ll) / 2
    smi = 200 * (ema2(rel, 3) / ema2(rng, 3))
    smi_ema = ema(smi, 3)
    return smi, smi_ema

# -----------------------------
# HİBRİT VERİ ÇEKME (BorsaPy + yfinance)
# -----------------------------
def process_symbol(sym, exchange, interval_str):
    df = None
    source = "None"
    
    # 1. Kaynak: BorsaPy (Sadece BIST için)
    if borsa_client and exchange == "BIST":
        try:
            bp_tf = {"1H": "1h", "4H": "4h", "1D": "1d", "1W": "1w"}.get(interval_str, "1d")
            df = borsa_client.get_data(sym, period="2y", interval=bp_tf)
            if df is not None and not df.empty and len(df) >= 50:
                source = "BorsaPy"
        except: pass

    # 2. Kaynak: yfinance (BorsaPy başarısızsa)
    if df is None or df.empty:
        try:
            ticker_sym = f"{sym}.IS" if exchange == "BIST" else sym
            yf_tf = {"1H": "1h", "4H": "1h", "1D": "1d", "1W": "1wk"}.get(interval_str, "1d")
            df = yf.download(ticker_sym, period="2y", interval=yf_tf, progress=False)
            
            if df is not None and not df.empty:
                # yfinance MultiIndex temizliği
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if len(df) >= 50:
                    source = "yfinance"
        except: return None

    if df is None or df.empty or len(df) < 50: return None

    # Sinyal Hesaplama
    try:
        smi, smi_ema = calc_smi(df)
        macd = ema(df["Close"], 12) - ema(df["Close"], 26)
        signal = ema(macd, 9)
        hist = macd - signal

        # float dönüştürme hatalarını önle (.values[-1])
        last_close = float(df["Close"].values[-1])
        prev_close = float(df["Close"].values[-2])
        change = ((last_close - prev_close) / prev_close) * 100
        
        l_smi, p_smi = float(smi.values[-1]), float(smi.values[-2])
        l_smi_ema, p_smi_ema = float(smi_ema.values[-1]), float(smi_ema.values[-2])
        l_hist, p_hist = float(hist.values[-1]), float(hist.values[-2])
        
        # SİNYAL KOŞULLARI
        cross_up = p_smi <= p_smi_ema and l_smi > l_smi_ema
        smi_neg = l_smi < 0
        hist_up = l_hist > p_hist
        
        ma200_val = float(df["Close"].rolling(200).mean().values[-1]) if len(df) >= 200 else 0
        above_ma200 = last_close > ma200_val
        
        # SMI MACD Kesişimi
        is_buy = cross_up and smi_neg and hist_up
        
        if is_buy:
            logging.info(f"✅ Sinyal Yakalandı: {sym} [{source}]")
            return {
                "Symbol": sym, "Exchange": exchange, "Period": interval_str,
                "Close": last_close, "Change": change,
                "Full_BUY": above_ma200, 
                "bar_time": df.index[-1].strftime('%Y-%m-%d %H:%M')
            }
        return None
    except Exception as e:
        logging.error(f"❌ Hesaplama Hatası ({sym}): {e}")
        return None

# -----------------------------
# ANA DÖNGÜ (MAIN)
# -----------------------------
async def async_main():
    if len(sys.argv) < 3:
        print("Kullanım: python tara.py tarama <PERİYOT> <MARKET>")
        return

    # Tickers.txt'den listeyi yükle
    if not os.path.exists(TICKERS_FILE):
        logging.error(f"❌ {TICKERS_FILE} bulunamadı!")
        return
        
    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        all_tickers = list(dict.fromkeys([l.strip().upper() for l in f if l.strip()]))

    PERIOD = sys.argv[2].upper()
    MARKET_TYPE = sys.argv[3].lower() if len(sys.argv) > 3 else "bist"
    
    # Market tipine göre sembolleri belirle
    if MARKET_TYPE == "bist":
        SYMBOLS = [(s, "BIST") for s in all_tickers]
    elif MARKET_TYPE == "emtia":
        SYMBOLS = [("GC=F", "COMEX"), ("SI=F", "COMEX")]
    elif MARKET_TYPE == "kripto":
        SYMBOLS = [("BTC-USD", "BINANCE"), ("ETH-USD", "BINANCE")]
    else:
        SYMBOLS = [(s, "BIST") for s in all_tickers]

    state = load_state()
    results = []
    
    logging.info(f"🚀 {PERIOD} Taraması Başladı ({len(SYMBOLS)} sembol)...")

    for sym, exc in SYMBOLS:
        row = process_symbol(sym, exc, PERIOD)
        if row:
            # Daha önce gönderilip gönderilmediğini kontrol et
            if state["last_sent"].get(f"{sym}_{PERIOD}") != row["bar_time"]:
                results.append(row)
        
        # Aşırı yüklenmeyi önlemek için küçük bekleme
        await asyncio.sleep(0.05)

    if results:
        msg = f"📊 <b>SMI & MACD TARAMA SONUÇLARI ({PERIOD})</b>\n\n"
        for r in results:
            icon = "✅" if r['Full_BUY'] else "🟡"
            msg += f"{icon} <b>{r['Symbol']}</b> | %{r['Change']:.2f} | Fiyat: {r['Close']:.2f}\n"
        
        tg_send_message(msg)
        
        for r in results[:15]: # Telegram sınırı için ilk 15 görsel
            path = await get_tv_screenshot(r['Symbol'], r['Exchange'], r['Period'])
            if path:
                tg_send_photo(path, f"#{r['Symbol']} ({r['Period']}) | Fiyat: {r['Close']:.2f}\nSinyal: SMI + MACD Alt Kesim")
                state["last_sent"][f"{r['Symbol']}_{r['Period']}"] = r["bar_time"]
            await asyncio.sleep(2)
        
        save_state(state)
    else:
        logging.info(f"🏁 {PERIOD} periyodunda yeni sinyal yok.")

if __name__ == "__main__":
    asyncio.run(async_main())
