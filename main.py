import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove  # type: ignore[import-not-found]
from telegram.ext import (  # type: ignore[import-not-found]
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from supabase import create_client, Client  # type: ignore[import-not-found]

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Supabase va Bot Sozlamalari (Environment Variables orqali xavfsiz o'qiladi)
SUPABASE_URL = os.getenv("https://pptswnqwapvmvtmqlspo.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("https://pptswnqwapvmvtmqlspo.supabase.co")

# Supabase mijozini yaratish
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ConversationHandler bosqichlari
WAITING_PHONE, WAITING_NAME = range(2)

# 1-Bosqich: /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_button = KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "Xush kelibsiz! Medilife platformasidan ro'yxatdan o'tish uchun iltimos, pastdagi tugma orqali telefon raqamingizni yuboring:",
        reply_markup=reply_markup
    )
    return WAITING_PHONE

# 2-Bosqich: Telefon raqamni qabul qilish va faqat ISMNI so'rash
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    phone_number = contact.phone_number
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number

    # Telefon raqamini vaqtinchalik xotiraga saqlaymiz
    context.user_data['phone_number'] = phone_number

    # Faqat ISMNI so'raymiz
    await update.message.reply_text(
        "Raqamingiz qabul qilindi! ✅\nEndi Medilife saytida ko'rinishi uchun **ismingizni** kiriting:",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    return WAITING_NAME

# 3-Bosqich: Ismni qabul qilish va Supabase'ga saqlash
async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.message.text.strip()
    phone_number = context.user_data.get('phone_number')
    user = update.message.from_user

    # Bazaga yoziladigan ma'lumotlar
    data = {
        "phone_number": phone_number,
        "chat_id": update.message.chat_id,
        "telegram_id": user.id,
        "first_name": first_name  # Foydalanuvchi kiritgan ism
    }

    try:
        # Supabase'ga saqlash yoki yangilash
        supabase.table("telegram_users").upsert(data, on_conflict="phone_number").execute()
        
        await update.message.reply_text(
            f"Rahmat, **{first_name}**! 🎉\nMa'lumotlaringiz saqlandi. Endi Medilife saytiga kirishingiz mumkin.",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Supabase xatoligi: {e}")
        await update.message.reply_text("❌ Xatolik yuz berdi. Qaytadan /start bosing.")

    return ConversationHandler.END

# Bekor qilish (Cancel)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Jarayon bekor qilindi. Qaytadan boshlash uchun /start bosing.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_PHONE: [MessageHandler(filters.CONTACT, handle_phone)],
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()