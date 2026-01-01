import os
import asyncio
import sqlite3
import requests
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ========== ENV ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render сам задаёт
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# ========== BOT ==========
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ========== DB ==========
conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT,
    lang TEXT DEFAULT 'ru',
    alerts INTEGER DEFAULT 0
)
""")
conn.commit()

# ========== TEXT ==========
TEXTS = {
    "ru": {
        "start": "🇺🇿 UzLife Bot\n\nПогода и экология Узбекистана.\n\n👉 Напиши город",
        "need_city": "❗ Сначала напиши город",
        "city_saved": "🏙 Город сохранён: {city}",
        "alerts_on": "🔔 Уведомления включены",
        "alerts_off": "🔕 Уведомления выключены",
    },
    "uz": {
        "start": "🇺🇿 UzLife Bot\n\nO‘zbekiston ob-havosi va ekologiyasi.\n\n👉 Shahar nomini yozing",
        "need_city": "❗ Avval shaharni kiriting",
        "city_saved": "🏙 Shahar saqlandi: {city}",
        "alerts_on": "🔔 Bildirishnomalar yoqildi",
        "alerts_off": "🔕 Bildirishnomalar o‘chirildi",
    }
}

# ========== KEYBOARD ==========
def kb(lang):
    if lang == "uz":
        return types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="🌦 Ob-havo"), types.KeyboardButton(text="🌫 Havo")],
                [types.KeyboardButton(text="💵 Valyuta")],
                [types.KeyboardButton(text="🔔 Bildirishnoma"), types.KeyboardButton(text="🌐 Til")]
            ],
            resize_keyboard=True
        )
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🌦 Погода"), types.KeyboardButton(text="🌫 Воздух")],
            [types.KeyboardButton(text="💵 Валюта")],
            [types.KeyboardButton(text="🔔 Уведомления"), types.KeyboardButton(text="🌐 Язык")]
        ],
        resize_keyboard=True
    )

# ========== HELPERS ==========
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

# ========== API ==========
def weather(city):
    r = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={
            "q": f"{city},UZ",
            "appid": OPENWEATHER_API_KEY,
            "units": "metric",
            "lang": "ru"
        },
        timeout=10
    )
    if r.status_code != 200:
        return None
    d = r.json()
    return d["main"]["temp"], d["main"]["feels_like"]

def currency():
    r = requests.get("https://api.exchangerate.host/latest?base=USD&symbols=UZS", timeout=10)
    if r.status_code != 200:
        return None
    return round(r.json()["rates"]["UZS"], 2)

# ========== HANDLERS ==========
@dp.message(CommandStart())
async def start(m: types.Message):
    set_user(m.from_user.id)
    _, lang, _ = get_user(m.from_user.id)
    await m.answer(TEXTS[lang]["start"], reply_markup=kb(lang))

@dp.message(F.text.in_(["🌦 Погода", "🌦 Ob-havo"]))
async def h_weather(m: types.Message):
    city, lang, _ = get_user(m.from_user.id)
    if not city:
        await m.answer(TEXTS[lang]["need_city"])
        return
    t, f = weather(city)
    await m.answer(f"🌦 {city}\n🌡 {t}°C\n🤒 {f}°C")

@dp.message(F.text.in_(["💵 Валюта", "💵 Valyuta"]))
async def h_currency(m: types.Message):
    r = currency()
    if r:
        await m.answer(f"💵 1 USD = {r} UZS")

@dp.message(F.text.in_(["🔔 Уведомления", "🔔 Bildirishnoma"]))
async def h_alerts(m: types.Message):
    city, lang, a = get_user(m.from_user.id)
    new = 0 if a else 1
    set_user(m.from_user.id, alerts=new)
    await m.answer(TEXTS[lang]["alerts_on"] if new else TEXTS[lang]["alerts_off"])

@dp.message(F.text.in_(["🌐 Язык", "🌐 Til"]))
async def h_lang(m: types.Message):
    city, lang, a = get_user(m.from_user.id)
    new = "uz" if lang == "ru" else "ru"
    set_user(m.from_user.id, lang=new)
    await m.answer("OK", reply_markup=kb(new))

@dp.message(F.text.regexp(r"^[A-Za-zА-Яа-я\s\-]+$"))
async def h_city(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    set_user(m.from_user.id, city=m.text)
    await m.answer(TEXTS[lang]["city_saved"].format(city=m.text))

# ========== WEB ==========
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

app = web.Application()
SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 10000)))
