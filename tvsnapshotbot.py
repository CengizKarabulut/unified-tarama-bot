import logging
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
# Bir önceki adımda hazırladığımız dosyadan import ediyoruz
# Fonksiyon adını take_screenshot_pro olarak değiştirdiysen burayı da güncelle
from tv_screenshot import take_screenshot_pro 

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot Token - Güvenlik için öncelik ortam değişkeninde
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7602646746:AAHdCroUOhOk_av9CXqn0gPnjJEUYIRLfJk")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Merhaba {name}! 🤖\n\n"
        "Profesyonel TradingView grafik botuna hoş geldin. Reklamlardan temizlenmiş, yüksek çözünürlüklü grafikler çekebilirim.\n\n"
        "Komutlar için: /help"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🚀 **Kullanım Kılavuzu**

1️⃣ **/snap [Borsa] [Sembol] [Periyot]**
Örnek: `/snap BIST THYAO 1D`
Örnek: `/snap BINANCE BTCUSDT 4H`

2️⃣ **/snaplist [Borsa] [Sembol1] [Sembol2]... [Periyot]**
Örnek: `/snaplist BIST THYAO ASELS EREGL 1D`

**Geçerli Periyotlar:** 1h, 4h, 1d, 1w
*(Not: Küçük/Büyük harf duyarlı değildir)*
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def snap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Hatalı kullanım! Örnek: `/snap BIST THYAO 1D`", parse_mode="Markdown")
        return

    exchange = args[0].upper()
    symbol = args[1].upper()
    interval = args[2].lower() # Screenshot fonksiyonu küçük harf bekler (1d, 4h vb.)

    status_msg = await update.message.reply_text(f"⏳ <b>{symbol}</b> grafiği temizleniyor ve hazırlanıyor...", parse_mode="HTML")

    try:
        # Yeni hazırladığımız profesyonel fonksiyonu çağırıyoruz
        path = await take_screenshot_pro(symbol, interval, exchange)
        
        if path and os.path.exists(path):
            with open(path, "rb") as photo:
                await update.message.reply_photo(
                    photo=photo, 
                    caption=f"📊 <b>{exchange}:{symbol}</b>\n⏱ Periyot: <code>{interval.upper()}</code>\n✅ Grafik başarıyla temizlendi.",
                    parse_mode="HTML"
                )
            await status_msg.delete()
        else:
            await status_msg.edit_text(f"❌ <b>{symbol}</b> grafiği alınamadı. Lütfen sembolün doğruluğunu kontrol et.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Snap hatası: {e}")
        await status_msg.edit_text(f"❌ Bir hata oluştu: <code>{str(e)}</code>", parse_mode="HTML")

async def snaplist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Hatalı kullanım! Örnek: `/snaplist BIST THYAO ASELS 1D`", parse_mode="Markdown")
        return

    exchange = args[0].upper()
    interval = args[-1].lower()
    symbols = [s.upper() for s in args[1:-1]]

    batch_msg = await update.message.reply_text(f"⏳ {len(symbols)} adet grafik sırayla çekiliyor...")

    for symbol in symbols:
        try:
            path = await take_screenshot_pro(symbol, interval, exchange)
            if path and os.path.exists(path):
                with open(path, "rb") as photo:
                    await update.message.reply_photo(photo=photo, caption=f"📊 {exchange}:{symbol} ({interval.upper()})")
            else:
                await update.message.reply_text(f"❌ {symbol} alınamadı.")
            
            # Playwright ve TradingView'i yormamak için listelerde bekleme süresini artırdık
            await asyncio.sleep(3) 
        except Exception as e:
            logger.error(f"Snaplist hatası ({symbol}): {e}")

    await batch_msg.edit_text("✅ Liste tamamlama işlemi bitti.")

def main():
    if not TOKEN or ":" not in TOKEN:
        print("Kritik Hata: Geçerli bir TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("snap", snap))
    application.add_handler(CommandHandler("snaplist", snaplist))

    print("--- Bot Aktif ve Komut Bekliyor ---")
    application.run_polling()

if __name__ == "__main__":
    main()
