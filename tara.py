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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
# FILES
# -----------------------------
STATE_FILE = "state.json"

# -----------------------------
# TELEGRAM
# -----------------------------
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID")

# -----------------------------
# TRADINGVIEW
# -----------------------------
TV_USERNAME = os.getenv("TV_USERNAME")
TV_PASSWORD = os.getenv("TV_PASSWORD")
TV_CHART_ID = os.getenv("TV_CHART_ID")

# -----------------------------
# STATE
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
        logging.error(f"Error saving state: {e}")

# -----------------------------
# TELEGRAM SENDERS
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
# TRADINGVIEW SCREENSHOT
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
            chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol={exchange}:{symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol={exchange}:{symbol}&interval={tv_interval}"
            await page.goto(chart_url, wait_until="networkidle")
            await asyncio.sleep(10)
            await page.screenshot(path=screenshot_path)
            return screenshot_path
        except Exception as e:
            logging.error(f"Screenshot Error: {e}")
            return None
        finally:
            if browser: await browser.close()

# -----------------------------
# CALCULATIONS (SMI & MACD)
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

def process_symbol(sym, exchange, interval_yf, period_str):
    try:
        ticker_sym = f"{sym}.IS" if exchange == "BIST" else sym
        df = yf.download(ticker_sym, period="2y", interval=interval_yf, progress=False)
        
        if df is None or df.empty: return None

        # --- MULTIINDEX FIX ---
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # ----------------------

        if len(df) < 50: return None

        smi, smi_ema = calc_smi(df)
        macd = ema(df["Close"], 12) - ema(df["Close"], 26)
        signal = ema(macd, 9)
        hist = macd - signal

        # --- SERIES TO FLOAT FIX ---
        last_close = float(df["Close"].values[-1])
        prev_close = float(df["Close"].values[-2])
        change = ((last_close - prev_close) / prev_close) * 100
        
        last_smi = float(smi.values[-1])
        prev_smi = float(smi.values[-2])
        last_smi_ema = float(smi_ema.values[-1])
        prev_smi_ema = float(smi_ema.values[-2])
        last_hist = float(hist.values[-1])
        prev_hist = float(hist.values[-2])
        # ---------------------------
        
        cross_up = prev_smi <= prev_smi_ema and last_smi > last_smi_ema
        smi_neg = last_smi < 0
        hist_neg = last_hist < 0
        hist_up = last_hist > prev_hist
        
        smi_macd_buy = cross_up and smi_neg and (hist_neg or hist_up)
        
        ma200_series = df["Close"].rolling(200).mean()
        ma200 = float(ma200_series.values[-1]) if len(df) >= 200 else 0
        above_ma200 = last_close > ma200
        
        full_buy = smi_macd_buy and above_ma200

        if smi_macd_buy:
            return {
                "Symbol": sym, "Exchange": exchange, "Period": period_str,
                "Close": last_close, "Change": change,
                "Full_BUY_Signal": full_buy, "SMI_MACD_BUY": True,
                "bar_time": df.index[-1].strftime('%Y-%m-%d %H:%M')
            }
        return None
    except Exception as e:
        logging.error(f"Error processing {sym}: {e}")
        return None

# -----------------------------
# MAIN
# -----------------------------
async def async_main():
    if len(sys.argv) < 3: 
        print("Kullanım: python tara.py <tarama_tipi> <periyot> <market>")
        return
        
    PERIOD = sys.argv[2].upper()
    MARKET_TYPE = sys.argv[3].lower() if len(sys.argv) > 3 else "bist"
    
    yf_intervals = {"1H": "1h", "4H": "1h", "1D": "1d", "1W": "1wk"}
    INTERVAL_YF = yf_intervals.get(PERIOD, "1d")

    BIST_STOCKS = ["AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "DOAS", "EGEEN", "EKGYO", "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL", "KONTR", "KOZAL", "KRDMD", "ODAS", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL", "THYAO", "TOASO", "TSKB", "TTKOM", "TUPRS", "VAKBN", "YKBNK"]
    
    SYMBOLS = [(s, "BIST") for s in BIST_STOCKS]
    if MARKET_TYPE == "emtia": SYMBOLS = [("GC=F", "COMEX"), ("SI=F", "COMEX")]
    elif MARKET_TYPE == "kripto": SYMBOLS = [("BTC-USD", "BINANCE"), ("ETH-USD", "BINANCE")]

    state = load_state()
    results = []
    for sym, exc in SYMBOLS:
        row = process_symbol(sym, exc, INTERVAL_YF, PERIOD)
        if row:
            last_sent = state["last_sent"].get(f"{sym}_{PERIOD}")
            if last_sent != row["bar_time"]:
                results.append(row)
        await asyncio.sleep(0.5)

    if results:
        msg = f"📊 <b>{PERIOD} TARAMA SONUÇLARI</b>\n\n"
        for r in results:
            icon = "✅" if r['Full_BUY_Signal'] else "🟡"
            msg += f"{icon} <b>{r['Symbol']}</b> | %{r['Change']:.2f} | {r['Close']:.2f}\n"
        tg_send_message(msg)
        for r in results:
            path = await get_tv_screenshot(r['Symbol'], r['Exchange'], r['Period'])
            if path:
                tg_send_photo(path, f"#{r['Symbol']} ({r['Period']}) | Fiyat: {r['Close']:.2f}")
                state["last_sent"][f"{r['Symbol']}_{r['Period']}"] = r["bar_time"]
        save_state(state)
    else:
        logging.info(f"{PERIOD} taramasında yeni sinyal yok.")

if __name__ == "__main__":
    asyncio.run(async_main())
