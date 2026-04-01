# ... (Üst kısımlar, importlar ve fonksiyonlar scanner.py ile benzer şekilde kalacak) ...
# Sadece async_main içindeki SYMBOLS kısmını tickers.txt'ye bağladım:

async def async_main():
    if len(sys.argv) < 3: return
    
    # tickers.txt dosyasını oku
    tickers = []
    if os.path.exists("tickers.txt"):
        with open("tickers.txt", "r", encoding="utf-8") as f:
            tickers = list(dict.fromkeys([l.strip().upper() for l in f if l.strip()]))
    
    PERIOD = sys.argv[2].upper()
    MARKET_TYPE = sys.argv[3].lower() if len(sys.argv) > 3 else "bist"

    if MARKET_TYPE == "bist":
        SYMBOLS = [(s, "BIST") for s in tickers]
    elif MARKET_TYPE == "emtia":
        SYMBOLS = [("GC=F", "COMEX"), ("SI=F", "COMEX")]
    elif MARKET_TYPE == "kripto":
        SYMBOLS = [("BTC-USD", "BINANCE"), ("ETH-USD", "BINANCE")]
    else:
        SYMBOLS = [(s, "BIST") for s in tickers]

    logging.info(f"🚀 {PERIOD} taraması {len(SYMBOLS)} sembol için başlatıldı.")
    
    # ... (Geri kalan döngü ve tarama mantığı aynı) ...
