import os
import sqlite3
import requests
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= DB =================
conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT,
    lang TEXT DEFAULT 'uz',
    alerts INTEGER DEFAULT 0
)
""")
conn.commit()

# ================= TEXT =================
TEXT = {
    "ru": {
        "start": (
            "🇺🇿 *UzLife Bot*\n\n"
            "Я показываю:\n"
            "🌦 погоду\n"
            "🌫 качество воздуха\n"
            "💵 курс валют\n\n"
            "👉 *Что нужно сделать:*\n"
            "1️⃣ Напишите название города\n"
            "2️⃣ Нажмите кнопку «Меню»"
        ),
        "city_saved": "🏙 Город сохранён: *{city}*",
        "need_city": "❗ Сначала напишите город",
        "weather_title": "🌦 *Погода в {city}*",
        "aqi_title": "🌫 *Качество воздуха в {city}*",
        "currency": "💵 *Курс валют*\n\n1 USD = *{rate} UZS*",
    },
    "uz": {
        "start": (
            "🇺🇿 *UzLife Bot*\n\n"
            "Bu bot sizga quyidagilarni ko‘rsatadi:\n"
            "🌦 ob-havo\n"
            "🌫 havo sifati\n"
            "💵 valyuta kursi\n\n"
            "👉 *Nima qilish kerak:*\n"
            "1️⃣ Shahar nomini yozing\n"
            "2️⃣ «Menyu» tugmasini bosing"
        ),
        "city_saved": "🏙 Shahar saqlandi: *{city}*",
        "need_city": "❗ Avval shahar nomini kiriting",
        "weather_title": "🌦 *{city} shahridagi ob-havo*",
        "aqi_title": "🌫 *{city} shahridagi havo sifati*",
        "currency": "💵 *Valyuta kursi*\n\n1 USD = *{rate} UZS*",
    }
}

# ================= KEYBOARDS =================
def reply_kb(lang):
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📋 Меню" if lang == "ru" else "📋 Menyu")],
            [
                types.KeyboardButton(text="🌐 Язык" if lang == "ru" else "🌐 Til"),
                types.KeyboardButton(text="🔔 Уведомления" if lang == "ru" else "🔔 Bildirishnoma"),
            ],
        ],
        resize_keyboard=True
    )

def menu_inline(lang):
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton("🌦 Погода" if lang == "ru" else "🌦 Ob-havo", callback_data="m_weather")],
            [types.InlineKeyboardButton("🌫 Воздух (AQI)" if lang == "ru" else "🌫 Havo sifati", callback_data="m_aqi")],
            [types.InlineKeyboardButton("💵 Валюта" if lang == "ru" else "💵 Valyuta", callback_data="m_currency")],
        ]
    )

# ================= HELPERS =================
def get_user(uid):
    cur.execute("SELECT city, lang, alerts FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def set_user(uid, city=None, lang=None, alerts=None):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    if city is not None:
        cur.execute("UPDATE users SET city=? WHERE user_id=?", (city, uid))
    if lang is not None:
        cur.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, uid))
    if alerts is not None:
        cur.execute("UPDATE users SET alerts=? WHERE user_id=?", (alerts, uid))
    conn.commit()

# ================= API =================
def get_weather(city, lang):
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={
            "q": f"{city},UZ",
            "appid": OPENWEATHER_API_KEY,
            "units": "metric",
            "lang": "ru" if lang == "ru" else "uz"
        },
        timeout=10
    )
    d = r.json()
    return {
        "temp": d["main"]["temp"],
        "feels": d["main"]["feels_like"],
        "humidity": d["main"]["humidity"],
        "wind": d["wind"]["speed"],
        "desc": d["weather"][0]["description"],
        "lat": d["coord"]["lat"],
        "lon": d["coord"]["lon"],
    }

def get_aqi(lat, lon):
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/air_pollution",
        params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
        timeout=10
    )
    return r.json()["list"][0]["main"]["aqi"]

def get_currency():
    r = requests.get("https://api.exchangerate.host/latest?base=USD&symbols=UZS", timeout=10)
    return round(r.json()["rates"]["UZS"], 2)

AQI_TEXT = {
    1: ("🟢 Yaxshi", "Havo toza, bemalol yurish mumkin"),
    2: ("🟡 O‘rtacha", "Sezgirlar ehtiyot bo‘lsin"),
    3: ("🟠 Yomon", "Faoliyatni cheklash tavsiya etiladi"),
    4: ("🔴 Juda yomon", "Tashqarida yurish tavsiya etilmaydi"),
    5: ("🟣 Xavfli", "Uyda qolish tavsiya etiladi"),
}

# ================= HANDLERS =================
@dp.message(CommandStart())
async def start(m: types.Message):
    set_user(m.from_user.id)
    _, lang, _ = get_user(m.from_user.id)
    await m.answer(TEXT[lang]["start"], reply_markup=reply_kb(lang), parse_mode="Markdown")

@dp.message(F.text.in_(["📋 Меню", "📋 Menyu"]))
async def show_menu(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    await m.answer("👇", reply_markup=menu_inline(lang))

@dp.message(F.text.in_(["🌐 Язык", "🌐 Til"]))
async def change_lang(m: types.Message):
    city, lang, a = get_user(m.from_user.id)
    new = "ru" if lang == "uz" else "uz"
    set_user(m.from_user.id, lang=new)
    await m.answer("OK", reply_markup=reply_kb(new))

@dp.message(F.text.regexp(r"^[A-Za-zА-Яа-я\s\-]+$"))
async def save_city(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    set_user(m.from_user.id, city=m.text)
    await m.answer(TEXT[lang]["city_saved"].format(city=m.text), parse_mode="Markdown")

# ================= CALLBACKS =================
async def cb_weather(c: types.CallbackQuery):
    await c.answer()
    city, lang, _ = get_user(c.from_user.id)
    w = get_weather(city, lang)
    text = (
        f"{TEXT[lang]['weather_title'].format(city=city)}\n\n"
        f"🌡 {w['temp']}°C (his etiladi {w['feels']}°C)\n"
        f"💧 Namlik: {w['humidity']}%\n"
        f"💨 Shamol: {w['wind']} m/s\n"
        f"☁️ {w['desc']}"
    )
    await c.message.answer(text, parse_mode="Markdown")

async def cb_aqi(c: types.CallbackQuery):
    await c.answer()
    city, lang, _ = get_user(c.from_user.id)
    w = get_weather(city, lang)
    aqi = get_aqi(w["lat"], w["lon"])
    level, rec = AQI_TEXT.get(aqi)
    await c.message.answer(
        f"{TEXT[lang]['aqi_title'].format(city=city)}\n\n"
        f"{level}\n"
        f"🧠 {rec}",
        parse_mode="Markdown"
    )

async def cb_currency(c: types.CallbackQuery):
    await c.answer()
    rate = get_currency()
    city, lang, _ = get_user(c.from_user.id)
    await c.message.answer(TEXT[lang]["currency"].format(rate=rate), parse_mode="Markdown")

# ================= REGISTER =================
dp.callback_query.register(cb_weather, F.data == "m_weather")
dp.callback_query.register(cb_aqi, F.data == "m_aqi")
dp.callback_query.register(cb_currency, F.data == "m_currency")

# ================= WEBHOOK =================
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL, allowed_updates=["message", "callback_query"])

app = web.Application()
SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)
app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 10000)))
