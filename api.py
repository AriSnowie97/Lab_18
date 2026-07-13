# api.py — FastAPI backend для Telegram Mini App
import json
import os

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_agent import process_message, reset_chat
from weather_api import fetch_full_weather, fetch_weather_by_coords, format_weather_card, get_forecast

app = FastAPI(title="WeatherBot API")

# ── CORS ──────────────────────────────────────────────────────────────────────
# Дозволяємо запити з GitHub Pages і Telegram (mini app завантажується з tg://)
ALLOWED_ORIGINS = [
    "https://arisnowie97.github.io",
    "https://web.telegram.org",
    "null",   # деякі браузери шлють null для локальних файлів
    *os.getenv("ALLOWED_ORIGINS", "").split(","),
]
ALLOWED_ORIGINS = [o for o in ALLOWED_ORIGINS if o]  # прибираємо порожні

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.github\.io",  # будь-який gh-pages домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Redis ─────────────────────────────────────────────────────────────────────
_redis_client: aioredis.Redis | None = None

async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _redis_client

# ── Моделі ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    user_id: str
    message: str

class SubscribeRequest(BaseModel):
    user_id: str
    time: str  # "HH:MM"

class UnsubscribeRequest(BaseModel):
    user_id: str

class ResetRequest(BaseModel):
    user_id: str

# ── /api/weather ──────────────────────────────────────────────────────────────
@app.get("/api/weather")
async def get_weather(
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    user_id: str | None = Query(None),
):
    """
    Погода по місту або GPS-координатах.
    Якщо передано lat+lon — використовуємо координати.
    Якщо передано city — шукаємо за назвою.
    """
    api_key = os.getenv("WEATHER_API_KEY")

    if lat is not None and lon is not None:
        weather = await fetch_weather_by_coords(lat, lon, api_key)
    elif city:
        weather = await fetch_full_weather(city, api_key)
    else:
        raise HTTPException(status_code=400, detail="Вкажіть city або lat+lon")

    if "error" in weather:
        raise HTTPException(status_code=404, detail=weather["error"])

    # Зберігаємо місто для daily-нотифікацій
    if user_id and weather.get("city"):
        r = await _get_redis()
        await r.set(f"city:{user_id}", weather["city"])

    return weather

# ── /api/forecast ─────────────────────────────────────────────────────────────
@app.get("/api/forecast")
async def get_forecast_endpoint(
    city: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
):
    """
    Прогноз на 5 днів (безкоштовний OWM API).
    Приймає city або lat+lon.
    """
    api_key = os.getenv("WEATHER_API_KEY")
    days = await get_forecast(api_key, city=city, lat=lat, lon=lon)
    if not days:
        raise HTTPException(status_code=404, detail="Не вдалось отримати прогноз")
    return {"days": days}

# ── /api/chat ─────────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """AI чат — та сама модель і та сама історія, що в Telegram."""
    try:
        reply = await process_message(req.user_id, req.message)
        return {"reply": reply}
    except RuntimeError as e:
        return {"reply": str(e)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── /api/chat/reset ───────────────────────────────────────────────────────────
@app.post("/api/chat/reset")
async def chat_reset(req: ResetRequest):
    """Скидає контекст розмови."""
    await reset_chat(req.user_id)
    return {"ok": True}

# ── /api/daily/{user_id} ──────────────────────────────────────────────────────
@app.get("/api/daily/{user_id}")
async def get_daily_history(user_id: str):
    """Повертає останні 30 щоденних звітів користувача."""
    r = await _get_redis()
    raw = await r.lrange(f"daily_history:{user_id}", 0, 29)
    reports = [json.loads(item) for item in raw]
    return {"reports": reports}

# ── /api/daily/subscribe ──────────────────────────────────────────────────────
@app.post("/api/daily/subscribe")
async def subscribe(req: SubscribeRequest):
    """Підписка на щоденні зведення."""
    try:
        hour, minute = map(int, req.time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        r = await _get_redis()
        await r.hset(f"daily:{req.user_id}", mapping={"hour": hour, "minute": minute})
        return {"ok": True, "time": req.time}
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Невірний формат часу (HH:MM)")

# ── /api/daily/unsubscribe ────────────────────────────────────────────────────
@app.post("/api/daily/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    """Відписка від щоденних зведень."""
    r = await _get_redis()
    await r.delete(f"daily:{req.user_id}")
    return {"ok": True}

# ── /api/daily/subscription/{user_id} ────────────────────────────────────────
@app.get("/api/daily/subscription/{user_id}")
async def get_subscription(user_id: str):
    """Повертає поточну підписку користувача."""
    r = await _get_redis()
    data = await r.hgetall(f"daily:{user_id}")
    if data:
        return {"subscribed": True, "hour": int(data["hour"]), "minute": int(data["minute"])}
    return {"subscribed": False}

# Статика тепер на GitHub Pages — цей рядок більше не потрібен
# app.mount("/", StaticFiles(directory="miniapp", html=True), name="miniapp")
