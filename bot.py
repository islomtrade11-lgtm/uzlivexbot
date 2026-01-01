import os
import asyncio
import sqlite3
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# ================= DB =================
conn = sqlite3.connect("users.db")
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

# ================= TEXTS =================
TEXTS = {
    "ru": {
        "start": "🇺🇿 UzLife Bot\n\nПогода, экология и жизнь в Узбекистане.\n\n👉 Напиши город",
        "city_saved": "🏙 Город сохранён: {city}",
        "need_city": "❗ Сначала напиши город",
        "weather_fail": "❌ Не удалось получить погоду",
        "aqi_fail": "❌ Не удалось получить AQI",
        "alerts_on": "🔔 Уведомления ВКЛЮЧЕНЫ ✅",
        "alerts_off": "🔕 Уведомления ВЫКЛЮЧЕНЫ ❌",
        "lang_set": "🌐 Язык переключён: Русский",
    },
    "uz": {
        "start": "🇺🇿 UzLife Bot\n\nO‘zbekiston ob-havosi va ekologiyasi.\n\n👉 Shahar nomini yozing",
        "city_saved": "🏙 Shahar saqlandi: {city}",
        "need_city": "❗ Avval shaharni kiriting",
        "weather_fail": "❌ Ob-havo olinmadi",
        "aqi_fail": "❌ Havo sifati olinmadi",
        "alerts_on": "🔔 Bildirishnomalar YOQILDI ✅",
        "alerts_off": "🔕 Bildirishnomalar O‘CHIRILDI ❌",
        "lang_set": "🌐 Til o‘zgartirildi: O‘zbekcha",
    }
}

# ================= KEYBOARD =================
def get_keyboard(lang):
    if lang == "uz":
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🌦 Ob-havo"), KeyboardButton(text="🌫 Havo (AQI)")],
                [KeyboardButton(text="💵 Valyuta")],
                [KeyboardButton(text="🔔 Bildirishnoma"), KeyboardButton(text="🌐 Til")],
            ],
            resize_keyboard=True
        )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌦 Погода"), KeyboardButton(text="🌫 Воздух (AQI)")],
            [KeyboardButton(text="💵 Курсы валют")],
            [KeyboardButton(text="🔔 Уведомления"), KeyboardButton(text="🌐 Язык")],
        ],
        resize_keyboard=True
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
def get_weather(city):
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
    if r.status_code != 200:
        return None
    a = r.json()["list"][0]
    return a["main"]["aqi"]

def get_currency():
    r = requests.get("https://api.exchangerate.host/latest?base=USD&symbols=UZS", timeout=10)
    if r.status_code != 200:
        return None
    return round(r.json()["rates"]["UZS"], 2)

# ================= HANDLERS =================
async def start(message: Message):
    uid = message.from_user.id
    set_user(uid)
    city, lang, alerts = get_user(uid)
    await message.answer(TEXTS[lang]["start"], reply_markup=get_keyboard(lang))

async def save_city(message: Message):
    uid = message.from_user.id
    city, lang, alerts = get_user(uid)
    set_user(uid, city=message.text)
    await message.answer(TEXTS[lang]["city_saved"].format(city=message.text))

async def weather(message: Message):
    uid = message.from_user.id
    city, lang, alerts = get_user(uid)
    if not city:
        await message.answer(TEXTS[lang]["need_city"])
        return
    w = get_weather(city)
    if not w:
        await message.answer(TEXTS[lang]["weather_fail"])
        return
    await message.answer(
        f"🌦 {city}\n🌡 {w['temp']}°C\n🤒 {w['feels']}°C\n☁️ {w['desc']}"
    )

async def aqi(message: Message):
    uid = message.from_user.id
    city, lang, alerts = get_user(uid)
    if not city:
        await message.answer(TEXTS[lang]["need_city"])
        return
    w = get_weather(city)
    a = get_aqi(w["lat"], w["lon"]) if w else None
    if not a:
        await message.answer(TEXTS[lang]["aqi_fail"])
        return
    await message.answer(f"🌫 AQI: {a}")

async def currency(message: Message):
    rate = get_currency()
    if rate:
        await message.answer(f"💵 1 USD = {rate} UZS")

async def toggle_alerts(message: Message):
    uid = message.from_user.id
    city, lang, alerts = get_user(uid)
    new = 0 if alerts else 1
    set_user(uid, alerts=new)
    await message.answer(TEXTS[lang]["alerts_on"] if new else TEXTS[lang]["alerts_off"])

async def toggle_lang(message: Message):
    uid = message.from_user.id
    city, lang, alerts = get_user(uid)
    new_lang = "uz" if lang == "ru" else "ru"
    set_user(uid, lang=new_lang)
    await message.answer(TEXTS[new_lang]["lang_set"], reply_markup=get_keyboard(new_lang))

# ================= ALERT LOOP =================
async def alert_loop(bot: Bot):
    while True:
        cur.execute("SELECT user_id, city, lang FROM users WHERE alerts=1 AND city IS NOT NULL")
        for uid, city, lang in cur.fetchall():
            w = get_weather(city)
            if w and w["temp"] >= 38:
                await bot.send_message(uid, f"🔥 {city}: {w['temp']}°C")
        await asyncio.sleep(3600)

# ================= MAIN =================
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start, CommandStart())
    dp.message.register(weather, F.text.in_(["🌦 Погода", "🌦 Ob-havo"]))
    dp.message.register(aqi, F.text.in_(["🌫 Воздух (AQI)", "🌫 Havo (AQI)"]))
    dp.message.register(currency, F.text.in_(["💵 Курсы валют", "💵 Valyuta"]))
    dp.message.register(toggle_alerts, F.text.in_(["🔔 Уведомления", "🔔 Bildirishnoma"]))
    dp.message.register(toggle_lang, F.text.in_(["🌐 Язык", "🌐 Til"]))
    dp.message.register(save_city, F.text.regexp(r"^[A-Za-zА-Яа-я\s\-]+$"))

    asyncio.create_task(alert_loop(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
