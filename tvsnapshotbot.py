import logging
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from tv_screenshot import take_screenshot

# Loglama ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot Token (Çevresel değişkenden al veya buraya yaz)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7602646746:AAHdCroUOhOk_av9CXqn0gPnjJEUYIRLfJk")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"Merhaba {name}! 🤖\n\n"
        "Ben TVSnapshot Bot. TradingView grafiklerini anlık olarak çekebilirim.\n"
        "Komutları öğrenmek için /help yazabilirsin."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🚀 **Kullanım Kılavuzu**

1️⃣ **/snap [Borsa] [Sembol] [Periyot]**
Tek bir sembolün grafiğini çeker.
Örnek: `/snap BIST THYAO 1D`
Örnek: `/snap BINANCE BTCUSDT 4H`

2️⃣ **/snaplist [Borsa] [Sembol1] [Sembol2]... [Periyot]**
Birden fazla sembolün grafiğini çeker.
Örnek: `/snaplist BIST THYAO ASELS EREGL 1D`

**Periyotlar:** 1, 3, 5, 15, 30, 45, 1H, 2H, 3H, 4H, 1D, 1W, 1M
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def snap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Hatalı kullanım! Örnek: `/snap BIST THYAO 1D`")
        return

    exchange = args[0].upper()
    symbol = args[1].upper()
    interval = args[2].lower()

    status_msg = await update.message.reply_text(f"⏳ {symbol} grafiği hazırlanıyor, lütfen bekleyin...")

    try:
        path = await take_screenshot(symbol, interval, exchange)
        if path and os.path.exists(path):
            with open(path, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=f"📊 {exchange}:{symbol} ({interval})")
            await status_msg.delete()
        else:
            await status_msg.edit_text(f"❌ {symbol} grafiği alınamadı.")
    except Exception as e:
        logger.error(f"Snap hatası: {e}")
        await status_msg.edit_text("❌ Bir hata oluştu.")

async def snaplist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("❌ Hatalı kullanım! Örnek: `/snaplist BIST THYAO ASELS 1D`")
        return

    exchange = args[0].upper()
    interval = args[-1].lower()
    symbols = [s.upper() for s in args[1:-1]]

    await update.message.reply_text(f"⏳ {len(symbols)} adet grafik hazırlanıyor, bu biraz zaman alabilir...")

    for symbol in symbols:
        try:
            path = await take_screenshot(symbol, interval, exchange)
            if path and os.path.exists(path):
                with open(path, "rb") as photo:
                    await update.message.reply_photo(photo=photo, caption=f"📊 {exchange}:{symbol} ({interval})")
            else:
                await update.message.reply_text(f"❌ {symbol} grafiği alınamadı.")
            await asyncio.sleep(2) # Telegram limitlerine takılmamak için
        except Exception as e:
            logger.error(f"Snaplist hatası ({symbol}): {e}")

def main():
    if not TOKEN:
        print("Hata: TELEGRAM_BOT_TOKEN bulunamadı!")
        return

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("snap", snap))
    application.add_handler(CommandHandler("snaplist", snaplist))

    print("Bot başlatıldı...")
    application.run_polling()

if __name__ == "__main__":
    main()
