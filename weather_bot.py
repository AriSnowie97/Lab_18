# weather_bot.py
import asyncio
import os
import aiohttp
import redis.asyncio as aioredis
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# --- Redis клієнт ---
redis: aioredis.Redis = None

async def get_redis() -> aioredis.Redis:
    global redis
    if redis is None:
        redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return redis

async def get_user_city(user_id: str) -> str | None:
    r = await get_redis()
    return await r.get(f"city:{user_id}")

async def save_user_city(user_id: str, city: str):
    r = await get_redis()
    await r.set(f"city:{user_id}", city)

# --- Погода ---
async def get_weather(city: str) -> dict:
    url = (
        f"http://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=uk"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

def get_wind_direction(degrees: float | None) -> str:
    if degrees is None:
        return "не визначено"
    directions = ["Пн", "Пн-Сх", "Сх", "Пд-Сх", "Пд", "Пд-Зх", "Зх", "Пн-Зх"]
    return directions[round(degrees / 45) % 8]

async def format_weather_data(data: dict) -> str:
    if data.get("cod") != 200:
        return "⚠️ Місто не знайдено. Перевірте правильність написання."
    main = data["main"]
    weather = data["weather"][0]
    wind = data["wind"]
    city = data["name"]
    country = data["sys"]["country"]

    return (
        f"📍 *Погода в місті {city}, {country}*\n\n"
        f"🌡️ Температура: {main['temp']} °C (відчувається як {main['feels_like']} °C)\n"
        f"☁️ Опис: {weather['description'].capitalize()}\n"
        f"💧 Вологість: {main['humidity']} %\n"
        f"💨 Вітер: {wind['speed']} м/с, напрямок: {get_wind_direction(wind.get('deg'))}\n"
        f"🔽 Тиск: {main['pressure']} hPa"
    )

# --- Ініціалізація бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Команди ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 Привіт! Я бот, який покаже вам актуальну погоду ☀️☁️🌧️.\n"
        "Введіть назву міста або скористайтесь командою /weather <місто>"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "🧾 *Доступні команди:*\n\n"
        "✅ /start – Запуск бота\n"
        "ℹ️ /info – Про бота\n"
        "🌤️ /weather <місто> – Погода в конкретному місті\n"
        "📍 /last\\_city – Ваше останнє запитане місто\n"
        "🛑 /exit – Завершити діалог\n\n"
        "✍️ Просто надішліть назву міста, щоб дізнатися погоду!",
        parse_mode="Markdown"
    )

@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    await message.reply(
        "🤖 *Цей бот показує поточну погоду.*\n"
        "📡 Дані надає OpenWeatherMap\n"
        "💻 Python + aiogram + Redis\n"
        "🚀 Хостинг: Railway",
        parse_mode="Markdown"
    )

@dp.message(Command("last_city"))
async def cmd_last_city(message: types.Message):
    user_id = str(message.from_user.id)
    city = await get_user_city(user_id)
    if city:
        await message.reply(f"📍 Ваше останнє місто: *{city}*", parse_mode="Markdown")
    else:
        await message.reply("❌ Ви ще не шукали погоду для жодного міста.")

@dp.message(Command("exit"))
async def cmd_exit(message: types.Message):
    await message.reply("👋 До зустрічі! Бот працює постійно ☁️.")

@dp.message(Command("weather"))
async def cmd_weather(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("🌇 Введіть місто після команди: /weather <місто>")
        return
    city = args[1]
    data = await get_weather(city)
    text = await format_weather_data(data)
    await message.reply(text, parse_mode="Markdown")
    await save_user_city(str(message.from_user.id), city)

# --- Повідомлення без команди: просто місто ---
@dp.message()
async def text_weather(message: types.Message):
    city = message.text.strip()
    data = await get_weather(city)
    text = await format_weather_data(data)
    await message.reply(text, parse_mode="Markdown")
    await save_user_city(str(message.from_user.id), city)

# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
