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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
# DOSYALAR
18	STATE_FILE = "state.json"
19	TICKERS_FILE = "tickers.txt"
20	
21	# -----------------------------
22	# TELEGRAM
23	# -----------------------------
24	TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN")
25	TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID")
26	
27	# -----------------------------
28	# TRADINGVIEW LOGIN
29	# -----------------------------
30	TV_USERNAME = os.getenv("TV_USERNAME")
31	TV_PASSWORD = os.getenv("TV_PASSWORD")
32	TV_CHART_ID = os.getenv("TV_CHART_ID")
33	
34	# -----------------------------
35	# TIMEFRAMES
36	# -----------------------------
37	TIMEFRAMES = ["1h", "4h", "1d", "1W"]
38	
39	# -----------------------------
40	# STATE
41	# -----------------------------
42	def load_state():
43	    if not os.path.exists(STATE_FILE):
44	        return {"last_sent": {tf: {} for tf in TIMEFRAMES}}
45	    try:
46	        with open(STATE_FILE, "r", encoding="utf-8") as f:
47	            return json.load(f)
48	    except:
49	        return {"last_sent": {tf: {} for tf in TIMEFRAMES}}
50	
51	def save_state(state):
52	    try:
53	        with open(STATE_FILE, "w", encoding="utf-8") as f:
54	            json.dump(state, f, ensure_ascii=False, indent=2)
55	    except Exception as e:
56	        logging.error(f"Error saving state: {e}")
57	
58	# -----------------------------
59	# TELEGRAM
60	# -----------------------------
61	def tg_send_message(text: str):
62	    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
63	    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
64	    try:
65	        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
66	    except: pass
67	
68	def tg_send_photo(photo_path: str, caption: str):
69	    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
70	    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
71	    try:
72	        with open(photo_path, 'rb') as f:
73	            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
74	    except: pass
75	
76	# -----------------------------
77	# TRADINGVIEW SCREENSHOT
78	# -----------------------------
79	async def get_tv_screenshot(symbol, interval):
80	    tv_intervals = {"1h": "60", "4h": "240", "1d": "D", "1W": "W"}
81	    tv_interval = tv_intervals.get(interval, "D")
82	    os.makedirs("screenshots", exist_ok=True)
83	    screenshot_path = f"screenshots/{symbol}_{interval}.png"
84	    async with async_playwright() as p:
85	        browser = None
86	        try:
87	            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
88	            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
89	            page = await context.new_page()
90	            chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol=BIST:{symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol=BIST:{symbol}&interval={tv_interval}"
91	            await page.goto(chart_url, wait_until="networkidle")
92	            await asyncio.sleep(10)
93	            await page.screenshot(path=screenshot_path)
94	            return screenshot_path
95	        except Exception as e:
96	            logging.error(f"TV Screenshot Hatası ({symbol}): {e}")
97	            return None
98	        finally:
99	            if browser: await browser.close()
100	
101	# -----------------------------
102	# RSI & SIGNAL
103	# -----------------------------
104	def rsi(series, length):
105	    delta = series.diff()
106	    gain = delta.clip(lower=0)
107	    loss = (-delta).clip(lower=0)
108	    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
109	    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
110	    rs = avg_gain / avg_loss.replace(0, np.nan)
111	    return 100 - (100 / (1 + rs))
112	
113	def fetch_and_signal(symbol, tf):
114	    try:
115	        ticker_sym = f"{symbol}.IS"
116	        yf_tf = {"1h": "1h", "4h": "1h", "1d": "1d", "1W": "1wk"}.get(tf, "1d")
117	        df = yf.download(ticker_sym, period="1y", interval=yf_tf, progress=False)
118	        if df is None or len(df) < 30: return False, None
119	        
120	        close = df["Close"].astype(float)
121	        vol = df["Volume"].astype(float)
122	        
123	        r = rsi(close, 7)
124	        r_last, r_prev = r.iloc[-1], r.iloc[-2]
125	        cond1 = r_last > 60
126	        cond2 = (r_prev <= 50) and (r_last > 50)
127	        
128	        v_last = vol.iloc[-1]
129	        v_avg = vol.tail(10).mean()
130	        cond3 = v_last > (v_avg * 1.5)
131	        
132	        if cond1 and cond2 and cond3:
133	            return True, df.index[-1].strftime('%Y-%m-%d %H:%M')
134	        return False, None
135	    except: return False, None
136	
137	# -----------------------------
138	# MAIN
139	# -----------------------------
140	async def async_main():
141	    now_trt = datetime.now(timezone.utc) + timedelta(hours=3)
142	    if not (now_trt.weekday() < 5 and 9.0 <= (now_trt.hour + now_trt.minute/60.0) <= 18.5):
143	        logging.info("Çalışma saatleri dışı.")
144	        return
145	
146	    tickers = []
147	    if os.path.exists(TICKERS_FILE):
148	        with open(TICKERS_FILE, "r") as f:
149	            tickers = [l.strip().upper() for l in f if l.strip()]
150	    
151	    if not tickers:
152	        tickers = ["AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "DOAS", "EGEEN", "EKGYO", "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL", "KONTR", "KOZAL", "KRDMD", "ODAS", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL", "THYAO", "TOASO", "TSKB", "TTKOM", "TUPRS", "VAKBN", "YKBNK"]
153	
154	    state = load_state()
155	    for tf in TIMEFRAMES:
156	        hits = []
157	        for sym in tickers:
158	            ok, bar_time = fetch_and_signal(sym, tf)
159	            if ok:
160	                if state["last_sent"][tf].get(sym) != bar_time:
161	                    hits.append((sym, bar_time))
162	        
163	        if hits:
164	            tg_send_message(f"<b>BIST Tarama | Periyot: {tf}</b>\nEşleşen: {len(hits)}")
165	            for sym, bar_time in hits[:15]:
166	                path = await get_tv_screenshot(sym, tf)
167	                if path:
168	                    tg_send_photo(path, f"<b>Hisse: {sym}</b>\nPeriyot: {tf}\nZaman: {bar_time}")
169	                    state["last_sent"][tf][sym] = bar_time
170	                await asyncio.sleep(1)
171	    save_state(state)
172	
173	if __name__ == "__main__":
174	    asyncio.run(async_main())
