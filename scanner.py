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

# BorsaPy entegrasyonu
try:
    from borsapy import Borsa
    borsa_client = Borsa()
except ImportError:
    logging.warning("BorsaPy kütüphanesi bulunamadı. Sadece yfinance kullanılacak.")
    borsa_client = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
# DOSYALAR & AYARLAR
# -----------------------------
STATE_FILE = "state.json"
TICKERS_FILE = "tickers.txt"
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TV_CHART_ID = os.getenv("TV_CHART_ID")
TIMEFRAMES = ["1h", "4h", "1d", "1W"]

# -----------------------------
# YARDIMCI FONKSİYONLAR (State & Telegram)
# -----------------------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_sent": {tf: {} for tf in TIMEFRAMES}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"last_sent": {tf: {} for tf in TIMEFRAMES}}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Error saving state: {e}")

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
# TRADINGVIEW SCREENSHOT
# -----------------------------
async def get_tv_screenshot(symbol, interval):
    tv_intervals = {"1h": "60", "4h": "240", "1d": "D", "1W": "W"}
    tv_interval = tv_intervals.get(interval, "D")
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{symbol}_{interval}.png"
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            page = await context.new_page()
            # BIST sembolleri için TradingView formatı
            chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol=BIST:{symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol=BIST:{symbol}&interval={tv_interval}"
            await page.goto(chart_url, wait_until="networkidle")
            await asyncio.sleep(10)
            await page.screenshot(path=screenshot_path)
            return screenshot_path
        except Exception as e:
            logging.error(f"TV Screenshot Hatası ({symbol}): {e}")
            return None
        finally:
            if browser: await browser.close()

# -----------------------------
# TEKNİK ANALİZ (RSI)
# -----------------------------
def rsi(series, length):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

# -----------------------------
# VERİ ÇEKME MOTORU (Waterfall)
# -----------------------------
def fetch_and_signal(symbol, tf):
    df = None
    source = "None"
    
    # 1. ADIM: BorsaPy ile çekmeyi dene
    if borsa_client:
        try:
            # BorsaPy periyot eşleme
            bp_tf = {"1h": "1h", "4h": "4h", "1d": "1d", "1W": "1w"}.get(tf, "1d")
            df = borsa_client.get_data(symbol, period="1y", interval=bp_tf)
            if df is not None and not df.empty and len(df) > 30:
                source = "BorsaPy"
        except Exception as e:
            logging.warning(f"BorsaPy hatası ({symbol}): {e}. yfinance'e geçiliyor...")

    # 2. ADIM: BorsaPy başarısızsa yfinance ile dene
    if df is None or df.empty:
        try:
            ticker_sym = f"{symbol}.IS"
            yf_tf = {"1h": "1h", "4h": "1h", "1d": "1d", "1W": "1wk"}.get(tf, "1d")
            df = yf.download(ticker_sym, period="1y", interval=yf_tf, progress=False)
            
            if df is not None and not df.empty:
                # MultiIndex başlıkları temizle (yfinance 0.2.x+ fix)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                if len(df) > 30:
                    source = "yfinance"
        except Exception as e:
            logging.error(f"yfinance hatası ({symbol}): {e}")
            return False, None

    # Veri hala yoksa çık
    if df is None or df.empty or len(df) < 30:
        return False, None

    # 3. ADIM: Sinyal Hesaplama
    try:
        close = df["Close"].astype(float)
        vol = df["Volume"].astype(float)
        
        r = rsi(close, 7)
        r_last = float(r.values[-1])
        r_prev = float(r.values[-2])
        
        # Koşul 1: RSI 60'ın üzerinde
        cond1 = r_last > 60
        # Koşul 2: RSI 50'yi yukarı kesmiş
        cond2 = (r_prev <= 50) and (r_last > 50)
        
        # Koşul 3: Hacim ortalamanın %50 üzerinde
        v_last = float(vol.values[-1])
        v_avg = float(vol.tail(10).mean())
        cond3 = v_last > (v_avg * 1.5)
        
        if cond1 and cond2 and cond3:
            logging.info(f"✅ Sinyal Bulundu: {symbol} [{tf}] Source: {source}")
            return True, df.index[-1].strftime('%Y-%m-%d %H:%M')
            
        return False, None
    except Exception as e:
        logging.error(f"Sinyal hesaplama hatası ({symbol}): {e}")
        return False, None

# -----------------------------
# ANA DÖNGÜ
# -----------------------------
async def async_main():
    # Çalışma saati kontrolü (Türkiye Saati)
    now_trt = datetime.now(timezone.utc) + timedelta(hours=3)
    if not (now_trt.weekday() < 5 and 9.0 <= (now_trt.hour + now_trt.minute/60.0) <= 18.5):
        logging.info("Piyasa kapalı. Tarama yapılmıyor.")
        return

    tickers = []
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r") as f:
            tickers = [l.strip().upper() for l in f if l.strip()]
    
    if not tickers:
        tickers = ["AKBNK", "THYAO", "EREGL", "SASA", "ASELS"] # Örnek liste

    state = load_state()
    for tf in TIMEFRAMES:
        hits = []
        logging.info(f"--- {tf} Taraması Başladı ---")
        for sym in tickers:
            ok, bar_time = fetch_and_signal(sym, tf)
            if ok:
                if state["last_sent"][tf].get(sym) != bar_time:
                    hits.append((sym, bar_time))
            await asyncio.sleep(0.1) # Sunucuları yormamak için kısa bekleme

        if hits:
            tg_send_message(f"📊 <b>{tf} RSI & Hacim Taraması</b>\nEşleşen hisse sayısı: {len(hits)}")
            for sym, bar_time in hits[:15]:
                path = await get_tv_screenshot(sym, tf)
                if path:
                    tg_send_photo(path, f"<b>Hisse: #{sym}</b>\nPeriyot: {tf}\nZaman: {bar_time}\nStrateji: RSI Cross + Hacim")
                    state["last_sent"][tf][sym] = bar_time
                await asyncio.sleep(2)
    save_state(state)

if __name__ == "__main__":
    asyncio.run(async_main())
