import asyncio
import json
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import redis.asyncio as aioredis
import os

from weather_api import fetch_full_weather, format_weather_card

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None

async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )
    return _redis_client

async def subscribe_user(user_id: str, time_str: str) -> bool:
    """
    Підписує користувача на щоденні сповіщення о вказаному часі (HH:MM).
    Повертає True якщо формат коректний.
    """
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return False
        r = await _get_redis()
        await r.hset(f"daily:{user_id}", mapping={"hour": hour, "minute": minute})
        return True
    except (ValueError, AttributeError):
        return False

async def unsubscribe_user(user_id: str):
    r = await _get_redis()
    await r.delete(f"daily:{user_id}")

async def get_subscription(user_id: str) -> dict | None:
    r = await _get_redis()
    data = await r.hgetall(f"daily:{user_id}")
    if data:
        return {"hour": int(data["hour"]), "minute": int(data["minute"])}
    return None

async def send_daily_weather(bot, user_id: str, hour: int, minute: int):
    """Надсилає щоденне зведення погоди конкретному користувачу."""
    now = datetime.now()
    if now.hour != hour or now.minute != minute:
        return

    r = await _get_redis()
    city = await r.get(f"city:{user_id}")
    if not city:
        return

    api_key = os.getenv("WEATHER_API_KEY")
    weather = await fetch_full_weather(city, api_key)
    if "error" in weather:
        return

    # Зберігаємо звіт в Redis для Mini App (max 30 записів)
    report = {
        "timestamp": now.isoformat(),
        "city": weather["city"],
        "country": weather["country"],
        "temp": weather["temp"],
        "feels_like": weather["feels_like"],
        "temp_min": weather["temp_min"],
        "temp_max": weather["temp_max"],
        "description": weather["description"],
        "icon": weather.get("icon", "01d"),
        "humidity": weather["humidity"],
        "wind_speed": weather["wind_speed"],
        "uv_description": weather["uv_description"],
    }
    history_key = f"daily_history:{user_id}"
    await r.lpush(history_key, json.dumps(report, ensure_ascii=False))
    await r.ltrim(history_key, 0, 29)  # зберігаємо тільки 30 останніх

    text = (
        f"🌅 *Доброго ранку! Ваше щоденне зведення погоди:*\n\n"
        + format_weather_card(weather)
    )
    try:
        await bot.send_message(int(user_id), text, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"Не вдалось надіслати daily для {user_id}: {e}")


async def daily_check_job(bot):
    """Перевіряє всіх підписаних користувачів і надсилає сповіщення."""
    r = await _get_redis()
    keys = await r.keys("daily:*")
    tasks = []
    for key in keys:
        user_id = key.split(":")[1]
        data = await r.hgetall(key)
        if data:
            tasks.append(send_daily_weather(
                bot, user_id, int(data["hour"]), int(data["minute"])
            ))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

def setup_scheduler(bot) -> AsyncIOScheduler:
    """Запускає APScheduler — перевірка кожну хвилину."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        daily_check_job,
        trigger=CronTrigger(minute="*"),  # кожну хвилину
        args=[bot],
        id="daily_weather",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started ✅")
    return scheduler
