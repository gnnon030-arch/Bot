import logging
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from supabase import create_client, Client

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

WAITING_PHONE, WAITING_NAME = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact_keyboard = KeyboardButton(
        text="📱 Telefon raqamni yuborish", request_contact=True
    )
    custom_keyboard = [[contact_keyboard]]
    reply_markup = ReplyKeyboardMarkup(
        custom_keyboard, resize_keyboard=True, one_time_keyboard=True
    )

    await update.message.reply_text(
        "Xush kelibsiz! Medilife platformasidan ro'yxatdan o'tish uchun iltimos, pastdagi tugma orqali telefon raqamingizni yuboring:",
        reply_markup=reply_markup,
    )
    return WAITING_PHONE


async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    raw_phone = contact.phone_number

    # Raqamni probelsiz va toza formatga keltirish (+998901234567)
    digits = "".join(filter(str.isdigit, raw_phone))
    clean_phone = f"+{digits}" if not raw_phone.startswith("+") else f"+{digits}"

    context.user_data["phone_number"] = clean_phone
    context.user_data["chat_id"] = update.effective_chat.id
    context.user_data["telegram_id"] = update.effective_user.id

    await update.message.reply_text(
        "Raqamingiz qabul qilindi! ✅\nEndi Medilife saytida ko'rinishi uchun ismingizni kiriting:"
    )
    return WAITING_NAME


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.message.text.strip()
    phone_number = context.user_data["phone_number"]
    chat_id = context.user_data["chat_id"]
    telegram_id = context.user_data["telegram_id"]

    try:
        supabase.from_("telegram_users").upsert(
            {
                "phone_number": phone_number,
                "chat_id": chat_id,
                "telegram_id": telegram_id,
                "first_name": first_name,
            },
            on_conflict="phone_number",
        ).execute()

        await update.message.reply_text(
            f"Rahmat, {first_name}! 🎉\nMa'lumotlaringiz saqlandi. Endi Medilife saytiga kirishingiz mumkin."
        )
    except Exception as e:
        logging.error(f"Supabase error: {e}")
        await update.message.reply_text(
            "Xatolik yuz berdi. Iltimos qaytadan urinib ko'ring."
        )

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Jarayon bekor qilindi.")
    return ConversationHandler.END


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is missing!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_PHONE: [
                MessageHandler(filters.CONTACT, handle_phone),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda u, c: u.message.reply_text(
                        "Iltimos, pastdagi tugmani bosing."
                    ),
                ),
            ],
            WAITING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()


if __name__ == "__main__":
    main()