# Unified Tarama Bot & TV Snapshot Bot

Bu depo, `taramabot` ve `tv-tarama-bot` projelerinin birleştirilmiş ve geliştirilmiş halidir. Ayrıca TradingView üzerinden anlık grafik ekran görüntüsü alma özelliği eklenmiştir.

## Özellikler
- **BIST Tarama:** SMI ve MACD indikatörlerine göre hisse taraması yapar.
- **Anlık Grafik:** Telegram üzerinden `/snap` komutu ile istediğiniz borsadan istediğiniz sembolün grafiğini alabilirsiniz.
- **Geliştirilmiş Telegram Bildirimleri:** Hata yönetimi ve loglama eklendi.
- **Playwright Entegrasyonu:** Grafik görüntüleme sorunları Playwright kullanılarak çözüldü.

## Kurulum

1. Gerekli kütüphaneleri yükleyin:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Çevresel değişkenleri ayarlayın:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_token"
   export TELEGRAM_CHAT_ID="your_chat_id"
   export TV_USERNAME="your_tradingview_username"
   export TV_PASSWORD="your_tradingview_password"
   ```

3. Botu çalıştırın:
   - Tarama botu için: `python tara.py`
   - Anlık grafik botu için: `python tvsnapshotbot.py`

## Komutlar (tvsnapshotbot.py)
- `/start`: Botu başlatır.
- `/help`: Yardım menüsünü gösterir.
- `/snap [BORSA] [SEMBOL] [PERİYOT]`: Tek grafik çeker.
- `/snaplist [BORSA] [S1] [S2]... [PERİYOT]`: Çoklu grafik çeker.
