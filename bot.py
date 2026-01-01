import os
import sqlite3
import requests
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ========= DB =========
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

# ========= TEXT =========
TEXT = {
    "ru": {
        "start": (
            "🇺🇿 *UzLife Bot*\n\n"
            "Актуальная информация по Узбекистану:\n"
            "🌦 погода · 🌫 воздух · 💵 валюта\n\n"
            "✍️ Напиши *город*, затем открой «Меню»"
        ),
        "city_saved": "🏙 Город сохранён: *{city}*",
        "need_city": "❗ Сначала напиши город",
        "alerts_on": "🔔 Уведомления *включены*",
        "alerts_off": "🔕 Уведомления *выключены*",
    },
    "uz": {
        "start": (
            "🇺🇿 *UzLife Bot*\n\n"
            "O‘zbekiston bo‘yicha ma’lumotlar:\n"
            "🌦 ob-havo · 🌫 havo · 💵 valyuta\n\n"
            "✍️ *Shahar* nomini yozing, so‘ng «Menyu» ni bosing"
        ),
        "city_saved": "🏙 Shahar saqlandi: *{city}*",
        "need_city": "❗ Avval shaharni kiriting",
        "alerts_on": "🔔 Bildirishnomalar *yoqildi*",
        "alerts_off": "🔕 Bildirishnomalar *o‘chirildi*",
    }
}

# ========= KEYBOARDS =========
def reply_kb(lang):
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📋 Меню" if lang == "ru" else "📋 Menyu")],
            [
                types.KeyboardButton(text="🌐 Язык" if lang == "ru" else "🌐 Til"),
                types.KeyboardButton(text="🔔 Уведомления" if lang == "ru" else "🔔 Bildirishnoma")
            ]
        ],
        resize_keyboard=True
    )

def menu_inline(lang):
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="🌦 Погода" if lang == "ru" else "🌦 Ob-havo",
                    callback_data="weather"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🌫 Воздух (AQI)" if lang == "ru" else "🌫 Havo (AQI)",
                    callback_data="aqi"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="💵 Валюта" if lang == "ru" else "💵 Valyuta",
                    callback_data="currency"
                )
            ]
        ]
    )

# ========= HELPERS =========
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

# ========= API =========
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
    return {
        "temp": d["main"]["temp"],
        "feels": d["main"]["feels_like"],
        "humidity": d["main"]["humidity"],
        "wind": d["wind"]["speed"],
        "desc": d["weather"][0]["description"]
    }

def aqi(city):
    w = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": f"{city},UZ", "appid": OPENWEATHER_API_KEY},
        timeout=10
    ).json()

    lat, lon = w["coord"]["lat"], w["coord"]["lon"]

    r = requests.get(
        "https://api.openweathermap.org/data/2.5/air_pollution",
        params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
        timeout=10
    )

    return r.json()["list"][0]["main"]["aqi"]

def currency():
    r = requests.get(
        "https://api.exchangerate.host/latest?base=USD&symbols=UZS",
        timeout=10
    )
    return round(r.json()["rates"]["UZS"], 2)

# ========= HANDLERS =========
@dp.message(CommandStart())
async def start(m: types.Message):
    set_user(m.from_user.id)
    _, lang, _ = get_user(m.from_user.id)
    await m.answer(
        TEXT[lang]["start"],
        reply_markup=reply_kb(lang),
        parse_mode="Markdown"
    )

@dp.message(F.text.in_(["📋 Меню", "📋 Menyu"]))
async def show_menu(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    await m.answer("👇", reply_markup=menu_inline(lang))

# -------- INLINE CALLBACKS (FIXED) --------
@dp.callback_query(F.data == "weather")
async def cb_weather(c: types.CallbackQuery):
    await c.answer()  # ОБЯЗАТЕЛЬНО
    city, lang, _ = get_user(c.from_user.id)

    if not city:
        await c.message.answer(TEXT[lang]["need_city"])
        return

    w = weather(city)
    if not w:
        await c.message.answer("❌ Не удалось получить данные")
        return

    text = (
        f"🌦 *Погода в {city}*\n\n"
        f"🌡 Температура: *{w['temp']}°C*\n"
        f"🤒 Ощущается: {w['feels']}°C\n"
        f"💧 Влажность: {w['humidity']}%\n"
        f"💨 Ветер: {w['wind']} м/с\n"
        f"☁️ {w['desc']}"
    )

    await c.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "aqi")
async def cb_aqi(c: types.CallbackQuery):
    await c.answer()  # ОБЯЗАТЕЛЬНО
    city, lang, _ = get_user(c.from_user.id)

    if not city:
        await c.message.answer(TEXT[lang]["need_city"])
        return

    value = aqi(city)

    levels = {
        1: "🟢 Хорошо",
        2: "🟡 Умеренно",
        3: "🟠 Плохо",
        4: "🔴 Очень плохо",
        5: "🟣 Опасно"
    }

    await c.message.answer(
        f"🌫 *Качество воздуха в {city}*\n\n"
        f"AQI: *{levels.get(value, value)}*",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "currency")
async def cb_currency(c: types.CallbackQuery):
    await c.answer()  # ОБЯЗАТЕЛЬНО
    rate = currency()
    await c.message.answer(
        f"💵 *Курс валют*\n\n"
        f"1 USD = *{rate} UZS*",
        parse_mode="Markdown"
    )

# -------- SETTINGS --------
@dp.message(F.text.in_(["🔔 Уведомления", "🔔 Bildirishnoma"]))
async def alerts(m: types.Message):
    _, lang, a = get_user(m.from_user.id)
    set_user(m.from_user.id, alerts=0 if a else 1)
    await m.answer(TEXT[lang]["alerts_on"] if not a else TEXT[lang]["alerts_off"])

@dp.message(F.text.in_(["🌐 Язык", "🌐 Til"]))
async def lang(m: types.Message):
    city, lang, a = get_user(m.from_user.id)
    new = "uz" if lang == "ru" else "ru"
    set_user(m.from_user.id, lang=new)
    await m.answer("OK", reply_markup=reply_kb(new))

@dp.message(F.text.regexp(r"^[A-Za-zА-Яа-я\s\-]+$"))
async def save_city(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    set_user(m.from_user.id, city=m.text)
    await m.answer(
        TEXT[lang]["city_saved"].format(city=m.text),
        parse_mode="Markdown"
    )

# ========= WEBHOOK =========
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

app = web.Application()
SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)
app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 10000)))
