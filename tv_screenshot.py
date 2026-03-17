import asyncio
import os
import logging
from playwright.async_api import async_playwright

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def take_screenshot(symbol, interval, exchange="BIST"):
    """
    TradingView üzerinden grafik ekran görüntüsü alır.
    """
    username = os.getenv("TV_USERNAME", "stockmarketlab")
    password = os.getenv("TV_PASSWORD", "stockmarketlab1987.")
    
    # TradingView interval mapping
    tv_intervals = {
        "1h": "60",
        "4h": "240",
        "1d": "D",
        "1W": "W"
    }
    tv_interval = tv_intervals.get(interval, "D")
    
    async with async_playwright() as p:
        # Tarayıcıyı başlat (Sandbox ortamında --no-sandbox gereklidir)
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            logging.info(f"TradingView'a giriş yapılıyor: {username}")
            # Login sayfasına git
            await page.goto("https://www.tradingview.com/#signin", timeout=60000)
            
            # Email ile giriş seçeneğini bul ve tıkla
            email_btn = page.get_by_text("Email", exact=True)
            if await email_btn.is_visible():
                await email_btn.click()
            
            # Kullanıcı adı ve şifreyi doldur
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            await page.click("button[type='submit']")
            
            # Girişin tamamlanmasını bekle (Çerezlerin yüklenmesi vb.)
            await page.wait_for_timeout(5000) 
            
            # Grafiğe git
            # Format: https://www.tradingview.com/chart/?symbol=EXCHANGE:SYMBOL&interval=INTERVAL
            chart_url = f"https://www.tradingview.com/chart/?symbol={exchange}:{symbol}&interval={tv_interval}"
            logging.info(f"Grafik yükleniyor: {chart_url}")
            await page.goto(chart_url, timeout=60000)
            
            # Grafiğin ve indikatörlerin yüklenmesi için bekle
            # TradingView ağır bir site olduğu için 15 saniye idealdir
            await page.wait_for_timeout(15000) 
            
            # Ekran görüntüsü al
            screenshot_dir = "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"{symbol}_{interval}.png")
            
            # Sadece grafik alanını veya tüm sayfayı al
            await page.screenshot(path=screenshot_path)
            
            logging.info(f"Ekran görüntüsü başarıyla kaydedildi: {screenshot_path}")
            await browser.close()
            return screenshot_path
            
        except Exception as e:
            logging.error(f"Ekran görüntüsü alınırken hata oluştu ({symbol}): {e}")
            # Hata durumunda sayfa içeriğini debug için kaydedebiliriz (isteğe bağlı)
            await browser.close()
            return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        sym = sys.argv[1]
        intv = sys.argv[2]
        exc = sys.argv[3] if len(sys.argv) > 3 else "BIST"
        asyncio.run(take_screenshot(sym, intv, exc))
