import os
import requests
import logging

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Çevresel değişkenlerden al
# Not: scanner.py veya tara.py içinde os.environ kullanarak bunları set edebilirsin
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# İstekler için bir session oluşturmak performansı artırır
session = requests.Session()

def send_message(text: str):
    """
    Telegram üzerinden metin mesajı gönderir.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logging.error("❌ Eksik Yapılandırma: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True # Link önizlemelerini kapatır, mesaj daha temiz durur
    }
    
    try:
        # timeout=10 ekleyerek botun sonsuza kadar asılı kalmasını önlüyoruz
        r = session.post(url, data=payload, timeout=10)
        r.raise_for_status()
        logging.info("✅ Mesaj başarıyla gönderildi.")
        return True
    except Exception as e:
        logging.error(f"❌ Telegram mesaj gönderme hatası: {e}")
        return False

def send_photo(image_path: str, caption: str = ""):
    """
    Telegram üzerinden fotoğraf gönderir.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logging.error("❌ Eksik Yapılandırma: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
        return False
        
    if not os.path.exists(image_path):
        logging.error(f"❌ Fotoğraf dosyası bulunamadı: {image_path}")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": CHAT_ID, 
        "caption": caption, 
        "parse_mode": "HTML"
    }
    
    try:
        with open(image_path, "rb") as f:
            files = {"photo": f}
            # Fotoğraf yükleme bazen uzun sürebilir, timeout=30 idealdir
            r = session.post(url, data=data, files=files, timeout=30)
        r.raise_for_status()
        logging.info(f"✅ Fotoğraf başarıyla gönderildi: {image_path}")
        return True
    except Exception as e:
        logging.error(f"❌ Telegram fotoğraf gönderme hatası: {e}")
        return False
