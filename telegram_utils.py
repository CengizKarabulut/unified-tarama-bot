import os
import requests
import logging

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Çevresel değişkenlerden veya varsayılan değerlerden al
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(text: str):
    """
    Telegram üzerinden metin mesajı gönderir.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logging.error("Eksik: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})
        r.raise_for_status()
        logging.info("Mesaj başarıyla gönderildi.")
        return True
    except Exception as e:
        logging.error(f"Telegram mesaj gönderme hatası: {e}")
        return False

def send_photo(image_path: str, caption: str = ""):
    """
    Telegram üzerinden fotoğraf gönderir.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logging.error("Eksik: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
        return False
        
    if not os.path.exists(image_path):
        logging.error(f"Fotoğraf dosyası bulunamadı: {image_path}")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as f:
            r = requests.post(url, data={"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}, files={"photo": f})
        r.raise_for_status()
        logging.info(f"Fotoğraf başarıyla gönderildi: {image_path}")
        return True
    except Exception as e:
        logging.error(f"Telegram fotoğraf gönderme hatası: {e}")
        return False
