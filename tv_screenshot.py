import asyncio
import os
import logging
from playwright.async_api import async_playwright

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def take_screenshot_pro(symbol, interval, exchange="BIST"):
    """
    TradingView üzerinden profesyonel, temizlenmiş grafik ekran görüntüsü alır.
    """
    # Kimlik bilgileri - Güvenlik için script içinde bırakma, .env dosyasından al
    username = os.getenv("TV_USERNAME")
    password = os.getenv("TV_PASSWORD")
    
    tv_intervals = {"1h": "60", "4h": "240", "1d": "D", "1W": "W"}
    tv_interval = tv_intervals.get(interval, "D")
    
    async with async_playwright() as p:
        # 'Stealth' benzeri ayarlar ile bot algılanmasını zorlaştırıyoruz
        browser = await p.chromium.launch(headless=True, args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled"
        ])
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080}, # Daha yüksek çözünürlük
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        try:
            # 1. Giriş Yap (Eğer kullanıcı adı/şifre varsa)
            if username and password:
                logging.info(f"Giriş yapılıyor: {username}")
                await page.goto("https://www.tradingview.com/#signin", wait_until="networkidle")
                
                # Email butonuna tıkla
                email_btn = page.get_by_text("Email", exact=True)
                if await email_btn.is_visible():
                    await email_btn.click()
                
                await page.fill("input[name='username']", username)
                await page.fill("input[name='password']", password)
                await page.click("button[type='submit']")
                await page.wait_for_timeout(3000) # Girişin işlenmesi için kısa bekleme

            # 2. Grafiğe Git (&theme=dark ile gece modu)
            chart_url = f"https://www.tradingview.com/chart/?symbol={exchange}:{symbol}&interval={tv_interval}&theme=dark"
            logging.info(f"Grafik yükleniyor: {chart_url}")
            await page.goto(chart_url, wait_until="domcontentloaded")

            # 3. Grafik Temizliği (CSS injection)
            # Bu kısım reklamları, headerları ve butonları gizler
            await page.add_style_tag(content="""
                .layout__area--left, .layout__area--top, .layout__area--right, 
                #header-toolbar, .p-ads-container, .tv-repro-banner,
                .button-S_1_8YvA, .is-interactive, .widgetbar-pages {
                    display: none !important;
                }
                .layout__area--center {
                    left: 0 !important;
                    top: 0 !important;
                    right: 0 !important;
                    bottom: 0 !important;
                }
            """)

            # 4. Grafiğin Yüklenmesini Bekle
            # Grafiğin ana render alanı gelene kadar bekle (maksimum 30 sn)
            try:
                await page.wait_for_selector(".chart-container-render-optimizer", timeout=30000)
            except:
                logging.warning("Grafik tam yüklenemedi, yine de çekim deneniyor...")

            await asyncio.sleep(5) # İndikatörlerin çizilmesi için son bir nefes payı

            # 5. Kaydet
            screenshot_dir = "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"{symbol}_{interval}.png")
            
            # Sadece grafik alanını hedefle (opsiyonel, tüm sayfa da olur)
            await page.screenshot(path=screenshot_path, full_page=False)
            
            logging.info(f"✅ Görsel kaydedildi: {screenshot_path}")
            return screenshot_path
            
        except Exception as e:
            logging.error(f"❌ Hata: {e}")
            return None
        finally:
            await browser.close()

if __name__ == "__main__":
    import sys
    # Örnek kullanım: python tv_screenshot.py THYAO 1h BIST
    sym = sys.argv[1] if len(sys.argv) > 1 else "THYAO"
    intv = sys.argv[2] if len(sys.argv) > 2 else "1d"
    exc = sys.argv[3] if len(sys.argv) > 3 else "BIST"
    asyncio.run(take_screenshot_pro(sym, intv, exc))
