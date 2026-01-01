import os
import asyncio
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

# ========= ENV =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

# ========= MEMORY =========
USER_CITY = {}

# ========= KEYBOARD =========
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🌦 Погода")],
        [KeyboardButton(text="🌫 Воздух (AQI)")],
        [KeyboardButton(text="🏙 Мой город")],
    ],
    resize_keyboard=True
)

# ========= SERVICES =========
def get_weather(city: str):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": f"{city},UZ",
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "ru"
    }
    r = requests.get(url, params=params, timeout=10)
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

def get_aqi(lat, lon):
    url = "https://api.openweathermap.org/data/2.5/air_pollution"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OPENWEATHER_API_KEY
    }
    r = requests.get(url, params=params, timeout=10)
    if r.status_code != 200:
        return None
    d = r.json()["list"][0]
    aqi_map = {
        1: "🟢 Хорошо",
        2: "🟡 Умеренно",
        3: "🟠 Плохо",
        4: "🔴 Очень плохо",
        5: "🟣 Опасно"
    }
    return {
        "aqi": aqi_map.get(d["main"]["aqi"], "—"),
        "pm2_5": d["components"]["pm2_5"],
        "pm10": d["components"]["pm10"]
    }

# ========= HANDLERS =========
async def start(message: Message):
    await message.answer(
        "🇺🇿 UzLife Bot\n\n"
        "Погода, экология и городская жизнь Узбекистана.\n\n"
        "👉 Напиши город (например: Ташкент)",
        reply_markup=main_kb
    )

async def save_city(message: Message):
    USER_CITY[message.from_user.id] = message.text
    await message.answer(f"🏙 Город сохранён: {message.text}")

async def weather_handler(message: Message):
    city = USER_CITY.get(message.from_user.id)
    if not city:
        await message.answer("❗ Сначала напиши город")
        return

    w = get_weather(city)
    if not w:
        await message.answer("❌ Не удалось получить погоду")
        return

    text = (
        f"🌦 Погода в {city}\n\n"
        f"🌡 Температура: {w['temp']}°C\n"
        f"🤒 Ощущается: {w['feels']}°C\n"
        f"💧 Влажность: {w['humidity']}%\n"
        f"💨 Ветер: {w['wind']} м/с\n"
        f"☁️ {w['desc']}"
    )
    await message.answer(text)

async def aqi_handler(message: Message):
    city = USER_CITY.get(message.from_user.id)
    if not city:
        await message.answer("❗ Сначала напиши город")
        return

    w = get_weather(city)
    if not w:
        await message.answer("❌ Не удалось получить данные")
        return

    a = get_aqi(w["lat"], w["lon"])
    if not a:
        await message.answer("❌ AQI недоступен")
        return

    text = (
        f"🌫 Качество воздуха в {city}\n\n"
        f"AQI: {a['aqi']}\n"
        f"PM2.5: {a['pm2_5']} µg/m³\n"
        f"PM10: {a['pm10']} µg/m³"
    )
    await message.answer(text)

# ========= MAIN =========
async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start, CommandStart())
    dp.message.register(weather_handler, F.text == "🌦 Погода")
    dp.message.register(aqi_handler, F.text == "🌫 Воздух (AQI)")
    dp.message.register(save_city, F.text.regexp(r"^[А-Яа-яA-Za-z\s\-]+$"))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
