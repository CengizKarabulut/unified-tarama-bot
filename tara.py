import json
import os
import asyncio
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
import numpy as np
from playwright.async_api import async_playwright
import logging
import sys
import yfinance as yf
from tradingview_ta import TA_Handler, Interval

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# -----------------------------
# FILES
18	STATE_FILE = "state.json"
19	
20	# -----------------------------
21	# TELEGRAM
22	# -----------------------------
23	TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN")
24	TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TG_CHAT_ID")
25	
26	# -----------------------------
27	# TRADINGVIEW
28	# -----------------------------
29	TV_USERNAME = os.getenv("TV_USERNAME")
30	TV_PASSWORD = os.getenv("TV_PASSWORD")
31	TV_CHART_ID = os.getenv("TV_CHART_ID")
32	
33	# -----------------------------
34	# STATE
35	# -----------------------------
36	def load_state():
37	    if not os.path.exists(STATE_FILE):
38	        return {"last_sent": {}}
39	    try:
40	        with open(STATE_FILE, "r", encoding="utf-8") as f:
41	            state = json.load(f)
42	            if "last_sent" not in state: state["last_sent"] = {}
43	            return state
44	    except:
45	        return {"last_sent": {}}
46	
47	def save_state(state):
48	    try:
49	        with open(STATE_FILE, "w", encoding="utf-8") as f:
50	            json.dump(state, f, ensure_ascii=False, indent=2)
51	    except Exception as e:
52	        logging.error(f"Error saving state: {e}")
53	
54	# -----------------------------
55	# TELEGRAM
56	# -----------------------------
57	def tg_send_message(text: str):
58	    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
59	    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
60	    try:
61	        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
62	    except: pass
63	
64	def tg_send_photo(photo_path: str, caption: str):
65	    if not TG_BOT_TOKEN or not TG_CHAT_ID: return
66	    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
67	    try:
68	        with open(photo_path, 'rb') as f:
69	            requests.post(url, data={"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}, files={"photo": f}, timeout=30)
70	    except: pass
71	
72	# -----------------------------
73	# TRADINGVIEW SCREENSHOT
74	# -----------------------------
75	async def get_tv_screenshot(symbol, exchange, interval_str):
76	    tv_intervals = {"1H": "60", "4H": "240", "1D": "D", "1W": "W"}
77	    tv_interval = tv_intervals.get(interval_str, "D")
78	    os.makedirs("screenshots", exist_ok=True)
79	    screenshot_path = f"screenshots/{symbol}_{interval_str}.png"
80	    async with async_playwright() as p:
81	        browser = None
82	        try:
83	            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
84	            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
85	            page = await context.new_page()
86	            chart_url = f"https://www.tradingview.com/chart/{TV_CHART_ID}/?symbol={exchange}:{symbol}&interval={tv_interval}" if TV_CHART_ID else f"https://www.tradingview.com/chart/?symbol={exchange}:{symbol}&interval={tv_interval}"
87	            await page.goto(chart_url, wait_until="networkidle")
88	            await asyncio.sleep(10)
89	            await page.screenshot(path=screenshot_path)
90	            return screenshot_path
91	        except Exception as e:
92	            logging.error(f"Screenshot Error: {e}")
93	            return None
94	        finally:
95	            if browser: await browser.close()
96	
97	# -----------------------------
98	# CALCULATIONS (SMI & MACD)
99	# -----------------------------
100	def ema(s, l): return s.ewm(span=l, adjust=False).mean()
101	def ema2(s, l): return ema(ema(s, l), l)
102	
103	def calc_smi(df):
104	    hh = df["High"].rolling(10).max()
105	    ll = df["Low"].rolling(10).min()
106	    rng = (hh - ll).replace(0, 0.000001)
107	    rel = df["Close"] - (hh + ll) / 2
108	    smi = 200 * (ema2(rel, 3) / ema2(rng, 3))
109	    smi_ema = ema(smi, 3)
110	    return smi, smi_ema
111	
112	def process_symbol(sym, exchange, interval_yf, period_str):
113	    try:
114	        ticker_sym = f"{sym}.IS" if exchange == "BIST" else sym
115	        df = yf.download(ticker_sym, period="2y", interval=interval_yf, progress=False)
116	        if df is None or df.empty or len(df) < 50: return None
117	
118	        smi, smi_ema = calc_smi(df)
119	        macd = ema(df["Close"], 12) - ema(df["Close"], 26)
120	        signal = ema(macd, 9)
121	        hist = macd - signal
122	
123	        last_close = float(df["Close"].iloc[-1])
124	        prev_close = float(df["Close"].iloc[-2])
125	        change = ((last_close - prev_close) / prev_close) * 100
126	        
127	        last_smi, prev_smi = float(smi.iloc[-1]), float(smi.iloc[-2])
128	        last_smi_ema, prev_smi_ema = float(smi_ema.iloc[-1]), float(smi_ema.iloc[-2])
129	        last_hist, prev_hist = float(hist.iloc[-1]), float(hist.iloc[-2])
130	        
131	        cross_up = prev_smi <= prev_smi_ema and last_smi > last_smi_ema
132	        smi_neg = last_smi < 0
133	        hist_neg = last_hist < 0
134	        hist_up = last_hist > prev_hist
135	        
136	        smi_macd_buy = cross_up and smi_neg and (hist_neg or hist_up)
137	        
138	        ma200 = df["Close"].rolling(200).mean().iloc[-1] if len(df) >= 200 else 0
139	        above_ma200 = last_close > ma200
140	        
141	        full_buy = smi_macd_buy and above_ma200
142	
143	        if smi_macd_buy:
144	            return {
145	                "Symbol": sym, "Exchange": exchange, "Period": period_str,
146	                "Close": last_close, "Change": change,
147	                "Full_BUY_Signal": full_buy, "SMI_MACD_BUY": True,
148	                "bar_time": df.index[-1].strftime('%Y-%m-%d %H:%M')
149	            }
150	        return None
151	    except Exception as e:
152	        logging.error(f"Error processing {sym}: {e}")
153	        return None
154	
155	# -----------------------------
156	# MAIN
157	# -----------------------------
158	async def async_main():
159	    if len(sys.argv) < 3: return
160	    PERIOD = sys.argv[2].upper()
161	    MARKET_TYPE = sys.argv[3].lower() if len(sys.argv) > 3 else "bist"
162	    
163	    yf_intervals = {"1H": "1h", "4H": "1h", "1D": "1d", "1W": "1wk"}
164	    INTERVAL_YF = yf_intervals.get(PERIOD, "1d")
165	
166	    BIST_STOCKS = ["AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "DOAS", "EGEEN", "EKGYO", "ENKAI", "EREGL", "FROTO", "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL", "KONTR", "KOZAL", "KRDMD", "ODAS", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL", "THYAO", "TOASO", "TSKB", "TTKOM", "TUPRS", "VAKBN", "YKBNK"]
167	    
168	    SYMBOLS = [(s, "BIST") for s in BIST_STOCKS]
169	    if MARKET_TYPE == "emtia": SYMBOLS = [("GC=F", "COMEX"), ("SI=F", "COMEX")]
170	    elif MARKET_TYPE == "kripto": SYMBOLS = [("BTC-USD", "BINANCE"), ("ETH-USD", "BINANCE")]
171	
172	    state = load_state()
173	    results = []
174	    for sym, exc in SYMBOLS:
175	        row = process_symbol(sym, exc, INTERVAL_YF, PERIOD)
176	        if row:
177	            last_sent = state["last_sent"].get(f"{sym}_{PERIOD}")
178	            if last_sent != row["bar_time"]:
179	                results.append(row)
180	        await asyncio.sleep(0.5)
181	
182	    if results:
183	        msg = f"📊 <b>{PERIOD} TARAMA SONUÇLARI</b>\n\n"
184	        for r in results:
185	            icon = "✅" if r['Full_BUY_Signal'] else "🟡"
186	            msg += f"{icon} <b>{r['Symbol']}</b> | %{r['Change']:.2f} | {r['Close']:.2f}\n"
187	        tg_send_message(msg)
188	        for r in results:
189	            path = await get_tv_screenshot(r['Symbol'], r['Exchange'], r['Period'])
190	            if path:
191	                tg_send_photo(path, f"#{r['Symbol']} ({r['Period']}) | Fiyat: {r['Close']:.2f}")
192	                state["last_sent"][f"{r['Symbol']}_{r['Period']}"] = r["bar_time"]
193	        save_state(state)
194	    else:
195	        logging.info(f"{PERIOD} taramasında yeni sinyal yok.")
196	
197	if __name__ == "__main__":
198	    asyncio.run(async_main())
