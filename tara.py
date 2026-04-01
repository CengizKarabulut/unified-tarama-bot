import json, os, asyncio, requests, logging, sys
import pandas as pd
import numpy as np
import yfinance as yf
from playwright.async_api import async_playwright

try:
    try:
        from borsapy import Borsa
    except ImportError:
        from borsa import Borsa
    borsa_client = Borsa()
except ImportError:
    borsa_client = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

STATE_FILE = "state.json"
TICKERS_FILE = "tickers.txt"
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TV_CHART_ID = os.getenv("TV_CHART_ID")

def load_state():
    if not os.path.exists(STATE_FILE): return {"last_sent": {}}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
            if "last_sent" not in st: st["last_sent"] = {}
            return st
    except: return {"last_sent": {}}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(state, f, indent=2)
    except: pass

def tg_send_photo(path, caption):
    if not TG_BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    try:
        with open(path, 'rb') as f:
            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
    except: pass

async def get_tv_screenshot(symbol, exchange, interval_str):
    tv_intervals = {"1H": "60", "4H": "240", "1D": "D", "1W": "W"}
    tv_interval = tv_intervals.get(interval_str, "D")
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{symbol}_{interval_str}.png"
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page()
            chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol={exchange}:{symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol={exchange}:{symbol}&interval={tv_interval}"
            await page.goto(chart_url, wait_until="networkidle")
            await asyncio.sleep(8)
            await page.screenshot(path=screenshot_path)
            await browser.close()
            return screenshot_path
        except: return None

def calc_smi(df):
    hh, ll = df["High"].rolling(10).max(), df["Low"].rolling(10).min()
    rng = (hh - ll).replace(0, 0.000001)
    rel = df["Close"] - (hh + ll) / 2
    ema = lambda s, l: s.ewm(span=l, adjust=False).mean()
    smi = 200 * (ema(ema(rel, 3), 3) / ema(ema(rng, 3), 3))
    return smi, ema(smi, 3)

def process_symbol(sym, exc, tf):
    df = None
    if borsa_client and exc == "BIST":
        try:
            df = borsa_client.get_data(sym, period="2y", interval={"1H":"1h","4H":"4h","1D":"1d","1W":"1w"}.get(tf, "1d"))
        except: pass
    if df is None or df.empty:
        try:
            df = yf.download(f"{sym}.IS" if exc=="BIST" else sym, period="2y", interval={"1H":"1h","4H":"1h","1D":"1d","1W":"1wk"}.get(tf, "1d"), progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        except: return None
    if df is None or len(df) < 50: return None
    try:
        smi, smi_ema = calc_smi(df)
        last_close, prev_close = float(df["Close"].values[-1]), float(df["Close"].values[-2])
        l_smi, p_smi = float(smi.values[-1]), float(smi.values[-2])
        l_smi_ema, p_smi_ema = float(smi_ema.values[-1]), float(smi_ema.values[-2])
        if p_smi <= p_smi_ema and l_smi > l_smi_ema and l_smi < 0:
            return {"Symbol": sym, "Exchange": exc, "Period": tf, "Close": last_close, "bar_time": df.index[-1].strftime('%Y-%m-%d %H:%M')}
        return None
    except: return None

async def async_main():
    if len(sys.argv) < 3: return
    if not os.path.exists(TICKERS_FILE): return
    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        tickers = [l.strip().upper() for l in f if l.strip()]
    PERIOD = sys.argv[2].upper()
    SYMBOLS = [(s, "BIST") for s in tickers]
    state = load_state()
    logging.info(f"TARA: {PERIOD} | {len(SYMBOLS)} hisse")
    results = []
    for sym, exc in SYMBOLS:
        row = process_symbol(sym, exc, PERIOD)
        if row and state["last_sent"].get(f"{sym}_{PERIOD}") != row["bar_time"]: results.append(row)
        await asyncio.sleep(0.05)
    if results:
        for r in results[:15]:
            path = await get_tv_screenshot(r['Symbol'], r['Exchange'], r['Period'])
            if path:
                tg_send_photo(path, f"#{r['Symbol']} ({r['Period']}) SMI+MACD Sinyali")
                state["last_sent"][f"{r['Symbol']}_{r['Period']}"] = r["bar_time"]
            await asyncio.sleep(2)
        save_state(state)

if __name__ == "__main__": asyncio.run(async_main())
