import logging
import os
import random
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from telegram import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove
)
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

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ptb_app = Application.builder().token(BOT_TOKEN).build()

# -------------------------------------------------------------
# MODELLAR
# -------------------------------------------------------------
class OTPRequest(BaseModel):
    phone_number: str

class OrderStatusUpdate(BaseModel):
    phone_number: str
    user_name: str
    status: str
    items_text: str
    total_price: str

# -------------------------------------------------------------
# TELEGRAMGA XABAR YUBORISH FUNKSIYASI
# -------------------------------------------------------------
async def send_telegram_message(chat_id: int, message_text: str):
    async with httpx.AsyncClient() as client:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message_text,
            "parse_mode": "Markdown"
        }
        await client.post(url, json=payload)

# -------------------------------------------------------------
# API ENDPOINTLAR
# -------------------------------------------------------------
@app.post("/send-otp")
async def send_otp(req: OTPRequest, background_tasks: BackgroundTasks):
    digits = "".join(filter(str.isdigit, req.phone_number))
    clean_phone = f"+{digits}"

    res = supabase.from_("telegram_users").select("chat_id").eq("phone_number", clean_phone).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="User not found in telegram_users")

    chat_id = res.data[0]["chat_id"]
    code = str(random.randint(1000, 9999))
    text = f"🔑 Medilife saytiga kirish kodingiz: {code}"

    background_tasks.add_task(send_telegram_message, chat_id, text)
    return {"status": "success", "code": code}

@app.post("/update-order-status")
async def update_order_status(req: OrderStatusUpdate, background_tasks: BackgroundTasks):
    digits = "".join(filter(str.isdigit, req.phone_number))
    clean_phone = f"+{digits}"

    res = supabase.from_("telegram_users").select("chat_id").eq("phone_number", clean_phone).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    chat_id = res.data[0]["chat_id"]

    message = (
        f"🔔 **Buyurtmangiz holati o'zgardi!**\n\n"
        f"Yangi holat: **{req.status}**\n\n"
        f"👤 {req.user_name}\n"
        f"📞 {clean_phone}\n\n"
        f"📦 **Tarkibi:**\n"
        f"{req.items_text}\n\n"
        f"💰 **Jami:** {req.total_price} so'm"
    )

    background_tasks.add_task(send_telegram_message, chat_id, message)
    return {"status": "success"}

# -------------------------------------------------------------
# TELEGRAM BOT LOGIKASI (YANGILANGAN)
# -------------------------------------------------------------

# Bosqichlar (States)
CHOOSING_ACTION, REG_PHONE, REG_NAME, REG_PASSWORD, LOGIN_PHONE, LOGIN_PASSWORD = range(6)

# Asosiy Bosh Menyular
MAIN_MENU = ReplyKeyboardMarkup([
    ["🔑 Kirish", "📝 Ro'yxatdan o'tish"]
], resize_keyboard=True)

LOGGED_IN_MENU = ReplyKeyboardMarkup([
    ["🌐 Saytga o'tish"],
    ["🚪 Akkauntdan chiqish"]
], resize_keyboard=True)

# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    
    # Baza orqali login bo'lganini tekshiramiz
    res = supabase.from_("telegram_users").select("*").eq("chat_id", user_id).execute()
    
    if res.data and res.data[0].get("is_logged_in"):
        name = res.data[0].get("first_name", "Foydalanuvchi")
        await update.message.reply_text(
            f"✨ **Xush kelibsiz, {name}!** 🌟\n\nSiz alaqachon akkauntingizga kirgansiz.",
            reply_markup=LOGGED_IN_MENU,
            parse_mode="Markdown"
        )
        return CHOOSING_ACTION

    await update.message.reply_text(
        "👋 **Medilife Rasmiy Botiga Xush Kelibsiz!**\n\nIltimos, davom etish uchun quyidagi tugmalardan birini tanlang:",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )
    return CHOOSING_ACTION

# --- RO'YXATDAN O'TISH (REGISTER) ---
async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]], resize_keyboard=True)
    await update.message.reply_text("📱 Ro'yxatdan o'tish uchun telefon raqamingizni yuboring:", reply_markup=kb)
    return REG_PHONE

async def handle_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.contact.phone_number if update.message.contact else update.message.text
    digits = "".join(filter(str.isdigit, raw_phone))
    
    if len(digits) < 9:
        await update.message.reply_text("❌ Iltimos, to'g'ri telefon raqam kiriting.")
        return REG_PHONE

    context.user_data["phone"] = f"+{digits}"
    await update.message.reply_text("👤 Ajoyib! Endi ismingizni kiriting:", reply_markup=ReplyKeyboardRemove())
    return REG_NAME

async def handle_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("🔑 Endi akkauntingiz uchun **6 xonali parol** o'ylab toping va kiriting:")
    return REG_PASSWORD

async def handle_reg_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    
    if len(password) < 6:
        await update.message.reply_text("⚠️ Parol kamida **6 ta belgidan** iborat bo'lishi kerak. Qaytadan kiriting:")
        return REG_PASSWORD

    phone = context.user_data["phone"]
    name = context.user_data["name"]
    chat_id = update.effective_chat.id

    # Bazaga saqlaymiz
    supabase.from_("telegram_users").upsert({
        "phone_number": phone,
        "chat_id": chat_id,
        "first_name": name,
        "password": password,
        "is_logged_in": True
    }, on_conflict="phone_number").execute()

    site_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Saytga o'tish", url="https://medilifeuz.lovable.app/login")]])

    await update.message.reply_text(
        f"🎉 **Tabriklaymiz, {name}!**\n\nAkkauntingiz muvaffaqiyatli yaratildi va tizimga kirdingiz! ✨",
        reply_markup=LOGGED_IN_MENU,
        parse_mode="Markdown"
    )
    await update.message.reply_text("Pastdagi tugma orqali saytga o'tishingiz mumkin:", reply_markup=site_btn)
    return CHOOSING_ACTION


# --- KIRISH (LOGIN) ---
async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]], resize_keyboard=True)
    await update.message.reply_text("🔑 Akkauntga kirish uchun telefon raqamingizni yuboring:", reply_markup=kb)
    return LOGIN_PHONE

async def handle_login_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.contact.phone_number if update.message.contact else update.message.text
    digits = "".join(filter(str.isdigit, raw_phone))
    clean_phone = f"+{digits}"

    # Supabase'dan tekshiramiz
    res = supabase.from_("telegram_users").select("*").eq("phone_number", clean_phone).execute()

    if not res.data:
        await update.message.reply_text(
            "❌ Bu telefon raqam ro'yxatdan o'tmagan! Iltimos, **Ro'yxatdan o'tish** tugmasini bosing.",
            reply_markup=MAIN_MENU
        )
        return CHOOSING_ACTION

    context.user_data["login_phone"] = clean_phone
    
    forgot_btn = InlineKeyboardMarkup([[InlineKeyboardButton("💡 Parol esdan chiqdimi?", url="https://t.me/abdulquddusodilov")]])
    
    await update.message.reply_text(
        "🔒 Parolingizni kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text("Agar parolingizni unutsangiz, pastdagi tugmani bosing:", reply_markup=forgot_btn)
    return LOGIN_PASSWORD

async def handle_login_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entered_password = update.message.text.strip()
    phone = context.user_data.get("login_phone")
    chat_id = update.effective_chat.id

    res = supabase.from_("telegram_users").select("*").eq("phone_number", phone).execute()

    if res.data and res.data[0].get("password") == entered_password:
        user_name = res.data[0].get("first_name", "Foydalanuvchi")
        
        # Logged in statusini yangilaymiz
        supabase.from_("telegram_users").update({"is_logged_in": True, "chat_id": chat_id}).eq("phone_number", phone).execute()

        site_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Saytga o'tish", url="https://medilifeuz.lovable.app/login")]])

        await update.message.reply_text(
            f"🌟 **Akkauntingizga xush kelibsiz, {user_name}!** ✨\n\nTizimga muvaffaqiyatli kirdingiz.",
            reply_markup=LOGGED_IN_MENU,
            parse_mode="Markdown"
        )
        await update.message.reply_text("Saytdan foydalanishingiz mumkin:", reply_markup=site_btn)
        return CHOOSING_ACTION
    else:
        forgot_btn = InlineKeyboardMarkup([[InlineKeyboardButton("💡 Parol esdan chiqdimi?", url="https://t.me/abdulquddusodilov")]])
        await update.message.reply_text("❌ **Xato parol!** Qaytadan urinib ko'ring yoki yordam oling:", reply_markup=forgot_btn)
        return LOGIN_PASSWORD


# --- AKKAUNTDAN CHIQISH (LOGOUT) ---
async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    supabase.from_("telegram_users").update({"is_logged_in": False}).eq("chat_id", chat_id).execute()

    await update.message.reply_text(
        "🚪 **Akkauntingizdan muvaffaqiyatli chiqdingiz.**\n\nQayta kirish uchun quyidagi menyudan foydalaning:",
        reply_markup=MAIN_MENU,
        parse_mode="Markdown"
    )
    return CHOOSING_ACTION

# --- SAYTGA O'TISH TUGMASI ---
async def handle_site_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    site_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Medilife Saytiga O'tish", url="https://medilifeuz.lovable.app/login")]])
    await update.message.reply_text("Saytga o'tish uchun quyidagi tugmani bosing:", reply_markup=site_btn)

# Handlerlarni sozlash
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        CHOOSING_ACTION: [
            MessageHandler(filters.Regex("^📝 Ro'yxatdan o'tish$"), start_register),
            MessageHandler(filters.Regex("^🔑 Kirish$"), start_login),
            MessageHandler(filters.Regex("^🚪 Akkauntdan chiqish$"), handle_logout),
            MessageHandler(filters.Regex("^🌐 Saytga o'tish$"), handle_site_open),
        ],
        REG_PHONE: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), handle_reg_phone)],
        REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reg_name)],
        REG_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reg_password)],
        LOGIN_PHONE: [MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), handle_login_phone)],
        LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login_password)],
    },
    fallbacks=[CommandHandler("start", start)],
)

ptb_app.add_handler(conv_handler)

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