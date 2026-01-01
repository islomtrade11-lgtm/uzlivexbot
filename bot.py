import os
import sqlite3
import requests
from aiogram import Bot, Dispatcher, executor, types

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

bot = Bot(token=BOT_TOKEN, parse_mode="Markdown")
dp = Dispatcher(bot)

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
TEXT = {  # ← БЕЗ ИЗМЕНЕНИЙ
    "ru": {...},
    "uz": {...}
}

# ========= KEYBOARDS =========
def reply_kb(lang):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(TEXT[lang]["menu"])
    kb.add(TEXT[lang]["lang_btn"], TEXT[lang]["alerts_btn"])
    return kb

def inline_menu(lang):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(TEXT[lang]["weather_btn"], callback_data="weather"))
    kb.add(types.InlineKeyboardButton(TEXT[lang]["aqi_btn"], callback_data="aqi"))
    kb.add(types.InlineKeyboardButton(TEXT[lang]["currency_btn"], callback_data="currency"))
    return kb

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
    if r.status_code != 200:
        return None

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

def get_aqi(city):
    w = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": f"{city},UZ", "appid": OPENWEATHER_API_KEY},
        timeout=10
    )
    if w.status_code != 200:
        return None

    w = w.json()
    lat, lon = w["coord"]["lat"], w["coord"]["lon"]

    r = requests.get(
        "https://api.openweathermap.org/data/2.5/air_pollution",
        params={"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY},
        timeout=10
    )
    return r.json()["list"][0]["main"]["aqi"]

def get_currency():
    try:
        r = requests.get("https://cbu.uz/ru/arkhiv-kursov-valyut/json/USD/", timeout=10)
        return r.json()[0]["Rate"]
    except:
        return None

# ========= HANDLERS =========
@dp.message_handler(commands=["start"])
async def start(m: types.Message):
    set_user(m.from_user.id)
    _, lang, _ = get_user(m.from_user.id)
    await m.answer(TEXT[lang]["start"], reply_markup=reply_kb(lang))

@dp.message_handler(lambda m: m.text in ["📋 Меню", "📋 Menyu"])
async def show_menu(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    await m.answer("👇", reply_markup=inline_menu(lang))

@dp.callback_query_handler(lambda c: c.data == "weather")
async def cb_weather(c: types.CallbackQuery):
    await c.answer()
    city, lang, _ = get_user(c.from_user.id)
    if not city:
        await c.message.answer(TEXT[lang]["need_city"])
        return

    w = get_weather(city, lang)
    if not w:
        await c.message.answer("❌ Не удалось получить данные о погоде")
        return

    await c.message.answer(TEXT[lang]["weather_text"].format(city=city, **w))

@dp.callback_query_handler(lambda c: c.data == "aqi")
async def cb_aqi(c: types.CallbackQuery):
    await c.answer()
    city, lang, _ = get_user(c.from_user.id)
    if not city:
        await c.message.answer(TEXT[lang]["need_city"])
        return

    value = get_aqi(city)
    if not value:
        await c.message.answer("❌ Не удалось получить AQI")
        return

    level, rec = TEXT[lang]["aqi_levels"][value]
    await c.message.answer(
        f"{TEXT[lang]['aqi_title'].format(city=city)}\n\n{level}\n🧠 {rec}"
    )

@dp.callback_query_handler(lambda c: c.data == "currency")
async def cb_currency(c: types.CallbackQuery):
    await c.answer()
    _, lang, _ = get_user(c.from_user.id)
    rate = get_currency()
    if not rate:
        await c.message.answer("❌ Не удалось получить курс валют")
        return
    await c.message.answer(TEXT[lang]["currency_text"].format(rate=rate))

@dp.message_handler(lambda m: m.text in ["🌐 Язык", "🌐 Til"])
async def change_lang(m: types.Message):
    city, lang, a = get_user(m.from_user.id)
    new = "uz" if lang == "ru" else "ru"
    set_user(m.from_user.id, lang=new)
    await m.answer(TEXT[new]["start"], reply_markup=reply_kb(new))

@dp.message_handler(lambda m: m.text in ["🔔 Уведомления", "🔔 Bildirishnoma"])
async def alerts(m: types.Message):
    _, lang, a = get_user(m.from_user.id)
    set_user(m.from_user.id, alerts=0 if a else 1)
    await m.answer(TEXT[lang]["alerts_on"] if not a else TEXT[lang]["alerts_off"])

@dp.message_handler(lambda m: m.text.replace(" ", "").isalpha())
async def save_city(m: types.Message):
    _, lang, _ = get_user(m.from_user.id)
    set_user(m.from_user.id, city=m.text)
    await m.answer(TEXT[lang]["city_saved"].format(city=m.text))

# ========= RUN =========
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
