import os
import sqlite3
import requests
from aiogram import Bot, Dispatcher, executor, types

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
dp = Dispatcher(bot)

# ================== DB ==================
conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    city TEXT,
    lang TEXT DEFAULT 'uz'
)
""")
conn.commit()

# ================== TEXT ==================
TEXT = {
    "ru": {
        "start": (
            "🇺🇿 *UzLife Bot*\n\n"
            "Я показываю актуальную информацию по Узбекистану:\n"
            "🌦 погода\n"
            "🌫 качество воздуха\n"
            "💵 курс валют\n\n"
            "*Как пользоваться:*\n"
            "1️⃣ Напишите город (например: Ташкент)\n"
            "2️⃣ Нажмите кнопку «Меню»"
        ),
        "city_saved": "🏙 Город сохранён: *{city}*",
        "menu": "📋 Меню",
        "lang": "🌐 Язык",
        "weather": "🌦 Погода",
        "aqi": "🌫 Воздух (AQI)",
        "currency": "💵 Валюта",
        "need_city": "❗ Сначала напишите город",
        "weather_text": (
            "🌦 *Погода в {city}*\n\n"
            "🌡 Температура: *{temp}°C*\n"
            "🤒 Ощущается: {feels}°C\n"
            "💧 Влажность: {humidity}%\n"
            "💨 Ветер: {wind} м/с\n"
            "☁️ {desc}"
        ),
        "aqi_text": (
            "🌫 *Качество воздуха в {city}*\n\n"
            "{level}\n"
            "🧠 {rec}"
        ),
        "currency_text": "💵 *Курс валют*\n\n1 USD = *{rate} UZS*",
    },
    "uz": {
        "start": (
            "🇺🇿 *UzLife Bot*\n\n"
            "Bu bot O‘zbekiston bo‘yicha quyidagi ma’lumotlarni ko‘rsatadi:\n"
            "🌦 ob-havo\n"
            "🌫 havo sifati\n"
            "💵 valyuta kursi\n\n"
            "*Qanday foydalaniladi:*\n"
            "1️⃣ Shahar nomini yozing (masalan: Toshkent)\n"
            "2️⃣ «Menyu» tugmasini bosing"
        ),
        "city_saved": "🏙 Shahar saqlandi: *{city}*",
        "menu": "📋 Menyu",
        "lang": "🌐 Til",
        "weather": "🌦 Ob-havo",
        "aqi": "🌫 Havo sifati",
        "currency": "💵 Valyuta",
        "need_city": "❗ Avval shahar nomini kiriting",
        "weather_text": (
            "🌦 *{city} shahridagi ob-havo*\n\n"
            "🌡 Harorat: *{temp}°C*\n"
            "🤒 His etiladi: {feels}°C\n"
            "💧 Namlik: {humidity}%\n"
            "💨 Shamol: {wind} m/s\n"
            "☁️ {desc}"
        ),
        "aqi_text": (
            "🌫 *{city} shahridagi havo sifati*\n\n"
            "{level}\n"
            "🧠 {rec}"
        ),
        "currency_text": "💵 *Valyuta kursi*\n\n1 USD = *{rate} UZS*",
    }
}

AQI_LEVELS = {
    1: ("🟢 Yaxshi", "Havo toza, bemalol yurish mumkin"),
    2: ("🟡 O‘rtacha", "Sezgir odamlar ehtiyot bo‘lsin"),
    3: ("🟠 Yomon", "Jismoniy faollikni cheklash tavsiya etiladi"),
    4: ("🔴 Juda yomon", "Tashqarida yurmaslik tavsiya etiladi"),
    5: ("🟣 Xavfli", "Uyda qolish tavsiya etiladi"),
}

# ================== HELPERS ==================
def get_user(uid):
    cur.execute("SELECT city, lang FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def set_user(uid, city=None, lang=None):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
    if city is not None:
        cur.execute("UPDATE users SET city=? WHERE user_id=?", (city, uid))
    if lang is not None:
        cur.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, uid))
    conn.commit()

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

# ================== KEYBOARDS ==================
def reply_kb(lang):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(TEXT[lang]["menu"])
    kb.add(TEXT[lang]["lang"])
    return kb

def inline_menu(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(TEXT[lang]["weather"], callback_data="weather"))
    kb.add(types.InlineKeyboardButton(TEXT[lang]["aqi"], callback_data="aqi"))
    kb.add(types.InlineKeyboardButton(TEXT[lang]["currency"], callback_data="currency"))
    return kb

# ================== HANDLERS ==================
@dp.message_handler(commands=["start"])
async def start(m: types.Message):
    set_user(m.from_user.id)
    city, lang = get_user(m.from_user.id)
    await m.answer(TEXT[lang]["start"], reply_markup=reply_kb(lang))

@dp.message_handler(lambda m: m.text in ["📋 Меню", "📋 Menyu"])
async def menu(m: types.Message):
    city, lang = get_user(m.from_user.id)
    if not city:
        await m.answer(TEXT[lang]["need_city"])
        return
    await m.answer("👇", reply_markup=inline_menu(lang))

@dp.message_handler(lambda m: m.text in ["🌐 Язык", "🌐 Til"])
async def change_lang(m: types.Message):
    city, lang = get_user(m.from_user.id)
    new = "ru" if lang == "uz" else "uz"
    set_user(m.from_user.id, lang=new)
    await m.answer(TEXT[new]["start"], reply_markup=reply_kb(new))

@dp.message_handler(lambda m: m.text.isalpha())
async def save_city(m: types.Message):
    set_user(m.from_user.id, city=m.text)
    city, lang = get_user(m.from_user.id)
    await m.answer(TEXT[lang]["city_saved"].format(city=city), reply_markup=reply_kb(lang))

@dp.callback_query_handler(lambda c: c.data == "weather")
async def cb_weather(c: types.CallbackQuery):
    await c.answer()
    city, lang = get_user(c.from_user.id)
    w = get_weather(city, lang)
    await c.message.answer(TEXT[lang]["weather_text"].format(city=city, **w))

@dp.callback_query_handler(lambda c: c.data == "aqi")
async def cb_aqi(c: types.CallbackQuery):
    await c.answer()
    city, lang = get_user(c.from_user.id)
    w = get_weather(city, lang)
    level, rec = AQI_LEVELS[get_aqi(w["lat"], w["lon"])]
    await c.message.answer(TEXT[lang]["aqi_text"].format(city=city, level=level, rec=rec))

@dp.callback_query_handler(lambda c: c.data == "currency")
async def cb_currency(c: types.CallbackQuery):
    await c.answer()
    city, lang = get_user(c.from_user.id)
    await c.message.answer(TEXT[lang]["currency_text"].format(rate=get_currency()))

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
