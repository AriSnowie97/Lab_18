# ai_agent.py
import asyncio
import json
import os
import time
import redis.asyncio as aioredis
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from weather_api import fetch_full_weather

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# ── Gemini клієнт (Ротація токенів) ──────────────────────────────────────────
class KeyManager:
    def __init__(self):
        self.keys = []
        for i in range(1, 11):
            k = os.getenv(f"GEMINI_API_KEY_{i}")
            if k:
                self.keys.append(k.replace('\n', '').replace('\r', '').replace(' ', '').replace('"', '').replace("'", '').strip())
                
        if not self.keys:
            single = os.getenv("GEMINI_API_KEY")
            if single:
                self.keys.append(single.replace('\n', '').replace('\r', '').replace(' ', '').replace('"', '').replace("'", '').strip())
                
        if not self.keys:
            raise ValueError("GEMINI_API_KEY_1... or GEMINI_API_KEY is missing in .env")
        self.cooldowns = {k: 0.0 for k in self.keys}
        self.current_idx = 0

    def get_next_key(self) -> str:
        now = time.time()
        for _ in range(len(self.keys)):
            key = self.keys[self.current_idx]
            self.current_idx = (self.current_idx + 1) % len(self.keys)
            if now >= self.cooldowns[key]:
                return key
        
        # Якщо всі ключі на кулдауні, просто беремо наступний
        key = self.keys[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.keys)
        return key

    def mark_exhausted(self, key: str, cooldown_sec: float = 60.0):
        self.cooldowns[key] = time.time() + cooldown_sec

_key_manager = KeyManager()

def _get_client(api_key: str | None = None) -> genai.Client:
    return genai.Client(api_key=api_key or _key_manager.get_next_key())

# ── Системний промпт ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ти — WeatherBot 🌤️, дружній AI-асистент з погоди у Telegram.

Твої можливості:
• Показувати поточну погоду в будь-якому місті світу
• Повідомляти УФ-індекс та рекомендації щодо сонцезахисту
• Пояснювати метеорологічні показники (вологість, тиск, видимість)
• Радити що одягнути або чи брати парасольку

Правила поведінки:
1. Відповідай тією мовою, якою пише користувач (українська, російська, англійська тощо)
2. Якщо місто не вказано в запиті — запитай або скажи що використаєш останнє збережене
3. ЗАВЖДИ викликай інструмент get_weather перед тим як давати відповідь про погоду — не вигадуй дані!
4. Будь дружнім і лаконічним. Використовуй емодзі доречно, але без надмірності
5. Якщо питання не стосується погоди — ввічливо поясни що ти спеціалізуєшся на погоді
6. Якщо місто не знайдено — запропонуй перевірити написання або назвати місто англійською
7. Давай практичні поради: "Сьогодні варто взяти парасольку ☂️", "УФ-індекс високий — нанеси крем SPF 50+ 🧴"
"""

# ── Інструменти для Gemini ────────────────────────────────────────────────────
TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_weather",
        description=(
            "Отримує поточну погоду для вказаного міста. "
            "Викликай цей інструмент щоразу, коли користувач питає про погоду, температуру, "
            "УФ-індекс, вологість, вітер або будь-які метеорологічні показники."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "city": types.Schema(
                    type=types.Type.STRING,
                    description="Назва міста (наприклад: Київ, London, New York)"
                )
            },
            required=["city"]
        )
    )
])]

CHAT_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)

# ── Redis ─────────────────────────────────────────────────────────────────────
_redis_client: aioredis.Redis | None = None

async def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )
    return _redis_client

async def _load_history(user_id: str) -> list[types.Content]:
    """Завантажує текстову історію з Redis і конвертує у формат Gemini."""
    r = await _get_redis()
    raw = await r.get(f"chat:{user_id}")
    if not raw:
        return []
    stored: list[dict] = json.loads(raw)
    return [
        types.Content(role=h["role"], parts=[types.Part(text=h["text"])])
        for h in stored
        if h.get("text")
    ]

async def _save_history(user_id: str, history: list[types.Content]):
    """Зберігає тільки текстові повідомлення (без function call/response)."""
    r = await _get_redis()
    stored = []
    for content in history[-20:]:
        text_parts = [
            p.text for p in content.parts
            if hasattr(p, "text") and p.text
        ]
        if text_parts:
            stored.append({"role": content.role, "text": " ".join(text_parts)})
    await r.set(
        f"chat:{user_id}",
        json.dumps(stored, ensure_ascii=False),
        ex=86400  # 24 години
    )

async def _clear_history(user_id: str):
    r = await _get_redis()
    await r.delete(f"chat:{user_id}")

# ── Виклик інструменту ────────────────────────────────────────────────────────
async def _execute_tool(name: str, args: dict, user_id: str) -> str:
    if name == "get_weather":
        city = args.get("city", "")
        weather = await fetch_full_weather(city, WEATHER_API_KEY)
        if "error" in weather:
            return weather["error"]
        # Зберігаємо місто для /last_city і daily-нотифікацій
        r = await _get_redis()
        await r.set(f"city:{user_id}", city)
        return json.dumps(weather, ensure_ascii=False)
    return "Інструмент не знайдено."

# ── Retry-хелпер для Gemini ──────────────────────────────────────────────────
async def _send_with_retry(chat, payload, max_retries: int = 4):
    """Надсилає повідомлення з ротацією ключів при помилках 429/503."""
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = await chat.send_message(payload)
            return response, chat
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err or "503" in err or "UNAVAILABLE" in err:
                last_exc = e
                current_key = getattr(chat, "_my_api_key", None)
                if current_key:
                    _key_manager.mark_exhausted(current_key)
                
                # Створюємо новий чат з новим ключем
                new_key = _key_manager.get_next_key()
                new_client = _get_client(new_key)
                
                # Переносимо історію
                history = list(chat.get_history())
                chat = new_client.aio.chats.create(
                    model="gemini-3.5-flash",
                    config=CHAT_CONFIG,
                    history=history
                )
                chat._my_api_key = new_key
                
                if attempt < max_retries:
                    await asyncio.sleep(1)
            else:
                raise

    raise RuntimeError(
        "⚠️ Gemini API: перевищено ліміт запитів на всіх ключах (429/503).\n"
        "Зачекай несколько минут и попробуй снова."
    )


# ── Головна функція агента ────────────────────────────────────────────────────
async def process_message(user_id: str, user_text: str) -> str:
    """
    Обробляє повідомлення через Gemini з function calling.
    Автоматично вмикає агентний цикл (виклик tools → отримання результату → фінальна відповідь).
    """
    current_key = _key_manager.get_next_key()
    client = _get_client(current_key)
    history = await _load_history(user_id)

    chat = client.aio.chats.create(
        model="gemini-3.5-flash",
        config=CHAT_CONFIG,
        history=history,
    )
    chat._my_api_key = current_key

    response, chat = await _send_with_retry(chat, user_text)

    # Агентний цикл: Gemini може кілька разів викликати tools
    for _ in range(5):
        has_tool_call = False
        tool_responses: list[types.Part] = []

        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call:
                    has_tool_call = True
                    result = await _execute_tool(
                        part.function_call.name,
                        dict(part.function_call.args),
                        user_id
                    )
                    tool_responses.append(
                        types.Part.from_function_response(
                            name=part.function_call.name,
                            response={"result": result}
                        )
                    )

        if not has_tool_call:
            break

        response, chat = await _send_with_retry(chat, tool_responses)

    try:
        final_text = response.text.strip() if response.text else "Вибач, не вдалось отримати відповідь 😔"
    except Exception:
        final_text = "Вибач, не вдалось отримати відповідь 😔"

    # Зберігаємо оновлену історію
    await _save_history(user_id, list(chat.get_history()))

    return final_text

async def reset_chat(user_id: str):
    """Скидає історію діалогу для користувача."""
    await _clear_history(user_id)
