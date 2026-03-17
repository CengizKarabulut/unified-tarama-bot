import json
import os
import asyncio
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import numpy as np
import borsapy as bp
from playwright.async_api import async_playwright
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
# DOSYALAR
# -----------------------------
STATE_FILE = "state.json"
TICKERS_FILE = "tickers.txt"

# -----------------------------
# TELEGRAM
# -----------------------------
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

# -----------------------------
# TRADINGVIEW LOGIN
# -----------------------------
TV_USERNAME = os.getenv("TV_USERNAME")
TV_PASSWORD = os.getenv("TV_PASSWORD")
TV_CHART_ID = os.getenv("TV_CHART_ID")

# -----------------------------
# TIMEFRAMES
# -----------------------------
TIMEFRAMES = ["1h", "4h", "1d", "1W"]

PERIOD_BY_TF = {
    "1h": "1ay",
    "4h": "3ay",
    "1d": "2y",
    "1W": "5y",
}

MAX_HITS_PER_TF = 15

# -----------------------------
# STATE
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

# -----------------------------
# TELEGRAM
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
# TRADINGVIEW SCREENSHOT (GELİŞTİRİLMİŞ)
# -----------------------------
async def get_tv_screenshot(symbol, interval):
    tv_intervals = {"1h": "60", "4h": "240", "1d": "D", "1W": "W"}
    tv_interval = tv_intervals.get(interval, "D")
    
    os.makedirs("screenshots", exist_ok=True)
    screenshot_path = f"screenshots/{symbol}_{interval}.png"
    
    async with async_playwright() as p:
        browser = None
        try:
            # Daha stabil bir tarayıcı başlatma
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'])
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = await context.new_page()
            
            # 1. Giriş Yap (Eğer bilgiler varsa)
            if TV_USERNAME and TV_PASSWORD:
                logging.info(f"TradingView girişi deneniyor...")
                await page.goto("https://www.tradingview.com/accounts/signin/", wait_until="networkidle")
                await page.fill("input[name='username']", TV_USERNAME)
                await page.fill("input[name='password']", TV_PASSWORD)
                await page.click("button[type='submit']")
                await asyncio.sleep(5) # Girişin tamamlanması için bekle
            
            # 2. Grafik Şablonuna Git
            if TV_CHART_ID:
                chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol=BIST:{symbol}&interval={tv_interval}"
            else:
                chart_url = f"https://www.tradingview.com/chart/?symbol=BIST:{symbol}&interval={tv_interval}"
            
            logging.info(f"Grafik açılıyor: {chart_url}")
            await page.goto(chart_url, wait_until="networkidle")
            
            # 3. Grafiğin ve İndikatörlerin Yüklenmesini Bekle
            # Chart container'ın gelmesini bekle
            try:
                await page.wait_for_selector(".chart-container", timeout=30000)
            except:
                logging.warning("Chart container bulunamadı, yine de devam ediliyor...")

            # İndikatörlerin ve verilerin tam yüklenmesi için ekstra süre
            logging.info("İndikatörlerin yüklenmesi için bekleniyor (15 sn)...")
            await asyncio.sleep(15) 
            
            # 4. Ekran Görüntüsü Al
            await page.screenshot(path=screenshot_path, full_page=False)
            logging.info(f"Ekran görüntüsü kaydedildi: {screenshot_path}")
            return screenshot_path
            
        except Exception as e:
            logging.error(f"TV Screenshot Hatası ({symbol}): {e}")
            return None
        finally:
            if browser: await browser.close()

# -----------------------------
# VERİ VE SİNYAL (Özetlenmiş)
# -----------------------------
def rsi(series, length):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def fetch_and_signal(symbol, tf):
    try:
        t = bp.Ticker(symbol)
        df = t.history(period=PERIOD_BY_TF[tf], interval=tf)
        if df is None or len(df) < 30: return False, None
        
        close = df["close"].astype(float)
        vol = df["volume"].astype(float)
        
        r = rsi(close, 7)
        r_last, r_prev = r.iloc[-1], r.iloc[-2]
        cond1 = r_last > 60
        cond2 = (r_prev <= 50) and (r_last > 50)
        
        v_last = vol.iloc[-1]
        v_avg = vol.tail(10).mean()
        cond3 = v_last > (v_avg * 1.5)
        
        if cond1 and cond2 and cond3:
            return True, df.index[-1]
        return False, df.index[-1]
    except: return False, None

# -----------------------------
# MAIN
# -----------------------------
async def async_main():
    # Zaman kontrolü (TRT 09:00-18:30)
    now_trt = datetime.now(timezone.utc) + timedelta(hours=3)
    if not (now_trt.weekday() < 5 and 9.0 <= (now_trt.hour + now_trt.minute/60.0) <= 18.5):
        logging.info("Çalışma saatleri dışı.")
        # Test için bu kontrolü geçici olarak devre dışı bırakmak isterseniz burayı yorum satırı yapın.
        return

    tickers = []
    if os.path.exists(TICKERS_FILE):
        with open(TICKERS_FILE, "r") as f:
            tickers = [l.strip().upper() for l in f if l.strip()]
    
    if not tickers:
        try: tickers = [s.upper() for s in bp.get_all_symbols()]
        except: return

    state = load_state()
    any_hits = False

    for tf in TIMEFRAMES:
        hits = []
        for sym in tickers:
            ok, bar_time = fetch_and_signal(sym, tf)
            if ok:
                bar_iso = bar_time.isoformat()
                if state["last_sent"][tf].get(sym) != bar_iso:
                    hits.append((sym, bar_iso))
        
        if hits:
            any_hits = True
            tg_send_message(f"<b>BIST Tarama | Periyot: {tf}</b>\nEşleşen: {len(hits)}")
            for sym, bar_iso in hits[:MAX_HITS_PER_TF]:
                caption = f"<b>Hisse: {sym}</b>\nPeriyot: {tf}\nZaman: {bar_iso}"
                path = await get_tv_screenshot(sym, tf)
                if path:
                    tg_send_photo(path, caption)
                else:
                    tg_send_message(f"Grafik alınamadı: {sym} ({tf})")
                state["last_sent"][tf][sym] = bar_iso
    
    if any_hits: save_state(state)

if __name__ == "__main__":
    asyncio.run(async_main())
