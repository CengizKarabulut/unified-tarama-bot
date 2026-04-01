import json, os, asyncio, requests, logging
from datetime import datetime, timezone, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
from playwright.async_api import async_playwright

# BorsaPy Entegrasyonu (Çift İhtimal Kontrollü)
try:
    try:
        from borsapy import Borsa
    except ImportError:
        from borsa import Borsa
    borsa_client = Borsa()
except ImportError:
    logging.warning("⚠️ BorsaPy bulunamadı. Sadece yfinance kullanılacak.")
    borsa_client = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

STATE_FILE = "state.json"
TICKERS_FILE = "tickers.txt"
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TV_CHART_ID = os.getenv("TV_CHART_ID")
TIMEFRAMES = ["1h", "4h", "1d", "1W"]

def get_tickers_from_file():
    if not os.path.exists(TICKERS_FILE):
        logging.error(f"❌ {TICKERS_FILE} bulunamadı!")
        return []
    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        return list(dict.fromkeys([l.strip().upper() for l in f if l.strip()]))

def load_state():
    if not os.path.exists(STATE_FILE): return {"last_sent": {tf: {} for tf in TIMEFRAMES}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {"last_sent": {tf: {} for tf in TIMEFRAMES}}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(state, f, indent=2)
    except Exception as e: logging.error(f"Error saving state: {e}")

def tg_send_photo(photo_path: str, caption: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as f:
            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
    except: pass

async def get_tv_screenshot(symbol, interval):
    tv_intervals = {"1h": "60", "4h": "240", "1d": "D", "1W": "W"}
    tv_interval = tv_intervals.get(interval, "D")
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{symbol}_{interval}.png"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol=BIST:{symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol=BIST:{symbol}&interval={tv_interval}"
        try:
            await page.goto(chart_url, wait_until="networkidle")
            await asyncio.sleep(10)
            await page.screenshot(path=screenshot_path)
            return screenshot_path
        except: return None
        finally: await browser.close()

def rsi(series, length):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def fetch_and_signal(symbol, tf):
    df = None
    if borsa_client:
        try:
            bp_tf = {"1h": "1h", "4h": "4h", "1d": "1d", "1W": "1w"}.get(tf, "1d")
            df = borsa_client.get_data(symbol, period="1y", interval=bp_tf)
        except: pass
    if df is None or df.empty:
        try:
            yf_tf = {"1h": "1h", "4h": "1h", "1d": "1d", "1W": "1wk"}.get(tf, "1d")
            df = yf.download(f"{symbol}.IS", period="1y", interval=yf_tf, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        except: return False, None
    if df is None or df.empty or len(df) < 30: return False, None
    try:
        close, vol = df["Close"].astype(float), df["Volume"].astype(float)
        r = rsi(close, 7)
        r_last, r_prev = float(r.values[-1]), float(r.values[-2])
        v_last, v_avg = float(vol.values[-1]), float(vol.tail(10).mean())
        if r_last > 60 and r_prev <= 50 and r_last > 50 and v_last > (v_avg * 1.5):
            return True, df.index[-1].strftime('%Y-%m-%d %H:%M')
        return False, None
    except: return False, None

async def async_main():
    tickers = get_tickers_from_file()
    if not tickers: return
    state = load_state()
    for tf in TIMEFRAMES:
        hits = []
        logging.info(f"Tarama: {tf} | {len(tickers)} hisse")
        for sym in tickers:
            ok, bar_time = fetch_and_signal(sym, tf)
            if ok and state["last_sent"][tf].get(sym) != bar_time: hits.append((sym, bar_time))
            await asyncio.sleep(0.05)
        if hits:
            for sym, bar_time in hits[:15]:
                path = await get_tv_screenshot(sym, tf)
                if path:
                    tg_send_photo(path, f"<b>#{sym}</b> ({tf})\nRSI & Hacim Sinyali")
                    state["last_sent"][tf][sym] = bar_time
                await asyncio.sleep(2)
    save_state(state)

if __name__ == "__main__": asyncio.run(async_main())
