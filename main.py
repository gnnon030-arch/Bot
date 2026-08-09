import logging
import os
import random
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from telegram import ReplyKeyboardMarkup, KeyboardButton, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import uvicorn
import httpx

load_dotenv()

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# FastAPI ilovasi
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Telegram Bot obyekti
ptb_app = Application.builder().token(BOT_TOKEN).build()

class OTPRequest(BaseModel):
    phone_number: str

@app.post("/send-otp")
async def send_otp(req: OTPRequest):
    digits = "".join(filter(str.isdigit, req.phone_number))
    clean_phone = f"+{digits}"

    res = (
        supabase.from_("telegram_users")
        .select("chat_id")
        .eq("phone_number", clean_phone)
        .execute()
    )

    if not res.data:
        raise HTTPException(
            status_code=404, detail="User not found in telegram_users"
        )

    chat_id = res.data[0]["chat_id"]
    code = str(random.randint(1000, 9999))

    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"🔑 Medilife saytiga kirish kodingiz: {code}",
        }
        await client.post(url, json=payload)

    return {"status": "success", "code": code}

WAITING_PHONE, WAITING_NAME = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [
            KeyboardButton(
                text="📱 Telefon raqamni yuborish", request_contact=True
            )
        ]
    ]
    await update.message.reply_text(
        "Xush kelibsiz! Medilife platformasidan ro'yxatdan o'tish uchun telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(
            kb, resize_keyboard=True, one_time_keyboard=True
        ),
    )
    return WAITING_PHONE

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.contact.phone_number
    digits = "".join(filter(str.isdigit, raw_phone))
    clean_phone = f"+{digits}"

    context.user_data["phone_number"] = clean_phone
    context.user_data["chat_id"] = update.effective_chat.id

    await update.message.reply_text(
        "Raqam qabul qilindi! Endi ismingizni kiriting:"
    )
    return WAITING_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.message.text.strip()
    phone = context.user_data["phone_number"]
    chat_id = context.user_data["chat_id"]

    supabase.from_("telegram_users").upsert(
        {"phone_number": phone, "chat_id": chat_id, "first_name": first_name},
        on_conflict="phone_number",
    ).execute()

    await update.message.reply_text(
        f"Rahmat, {first_name}! Endi saytdan kirishingiz mumkin."
    )
    return ConversationHandler.END

# Bot buyruqlarini sozlash
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        WAITING_PHONE: [MessageHandler(filters.CONTACT, handle_phone)],
        WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
    },
    fallbacks=[],
)
ptb_app.add_handler(conv_handler)

# FastAPI va Telegram Botni bitta async siklda ishga tushirish (Lifespan Event)
@app.on_event("startup")
async def on_startup():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.updater.start_polling(drop_pending_updates=True)

@app.on_event("shutdown")
async def on_shutdown():
    await ptb_app.updater.stop()
    await ptb_app.stop()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)