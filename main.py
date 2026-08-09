
import os
import random
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    ContextTypes, ConversationHandler, filters
)
from supabase import create_client, Client
import asyncio

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Web server (FastAPI)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class OTPRequest(BaseModel):
    phone_number: str

# Telegram Bot qismi
WAITING_PHONE, WAITING_NAME = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]]
    await update.message.reply_text(
        "Xush kelibsiz! Medilife platformasidan ro'yxatdan o'tish uchun telefon raqamingizni yuboring:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
    )
    return WAITING_PHONE

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.contact.phone_number
    digits = "".join(filter(str.isdigit, raw_phone))
    clean_phone = f"+{digits}"
    
    context.user_data["phone_number"] = clean_phone
    context.user_data["chat_id"] = update.effective_chat.id
    
    await update.message.reply_text("Raqam qabul qilindi! Endi ismingizni kiriting:")
    return WAITING_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.message.text.strip()
    phone = context.user_data["phone_number"]
    chat_id = context.user_data["chat_id"]
    
    supabase.from_("telegram_users").upsert({
        "phone_number": phone,
        "chat_id": chat_id,
        "first_name": first_name
    }, on_conflict="phone_number").execute()
    
    await update.message.reply_text(f"Rahmat, {first_name}! Endi saytdan kirishingiz mumkin.")
    return ConversationHandler.END

# Sayt "Kod olish"ni bosganda ishlaydigan API
@app.post("/send-otp")
async def send_otp(req: OTPRequest):
    clean_phone = "+" + "".join(filter(str.isdigit, req.phone_number))
    
    # Bazadan chat_id topamiz
    res = supabase.from_("telegram_users").select("chat_id").eq("phone_number", clean_phone).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="User not found")
        
    chat_id = res.data[0]["chat_id"]
    code = str(random.randint(1000, 9999))
    
    # Telegram'ga kod yuboramiz
    await bot_app.bot.send_message(
        chat_id=chat_id, 
        text=f"🔑 Medilife saytiga kirish kodingiz: {code}"
    )
    
    return {"status": "success", "code": code}

def main():
    global bot_app
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_PHONE: [MessageHandler(filters.CONTACT, handle_phone)],
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        },
        fallbacks=[]
    )
    bot_app.add_handler(conv_handler)
    
    # Bot va API birgalikda ishlaydi
    loop = asyncio.get_event_loop()
    loop.create_task(bot_app.initialize())
    loop.create_task(bot_app.start())
    loop.create_task(bot_app.updater.start_polling())
    
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()