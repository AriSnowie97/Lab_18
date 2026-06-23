# ai_agent.py
import json
import os
import google.generativeai as genai
import redis.asyncio as aioredis
from weather_api import fetch_full_weather, format_weather_card

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

# ── Системний промпт ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Ти — WeatherBot 🌤️, дружній AI-асистент з погоди у Telegram.

Твої можливості:
• Показувати поточну погоду в будь-якому місті світу
• Повідомляти УФ-індекс та рекомендації щодо сонцезахисту
• Пояснювати метеорологічні показники (вологість, тиск, видимість)
• Радити що одягнути або чи брати парасольку

Правила поведінки:
1. Відповідай тією мовою, якою пише користувач (українська, російська, англійська тощо)
2. Якщо місто не вказано в запиті — запитай, або скажи що використаєш останнє збережене
3. ЗАВЖДИ викликай інструмент get_weather перед тим як давати відповідь про погоду — не вигадуй дані!
4. Будь дружнім і лаконічним. Використовуй емодзі доречно, але без надмірності
5. Якщо питання не стосується погоди — ввічливо поясни що ти спеціалізуєшся на погоді
6. Якщо місто не знайдено — запропонуй перевірити написання або назвати місто англійською
7. Давай практичні поради: "Сьогодні варто взяти парасольку ☂️", "УФ-індекс високий — нанеси крем SPF 50+ 🧴"
"""

# ── Визначення інструментів для Gemini ───────────────────────────────────────
TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "Отримує поточну погоду для вказаного міста. "
            "Викликай цей інструмент щоразу, коли користувач питає про погоду, температуру, "
            "УФ-індекс, вологість, вітер або будь-які метеорологічні показники."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Назва міста (наприклад: Київ, London, New York)",
                }
            },
            "required": ["city"],
        },
    }
]

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

async def _load_history(user_id: str) -> list[dict]:
    r = await _get_redis()
    raw = await r.get(f"chat:{user_id}")
    if raw:
        return json.loads(raw)
    return []

async def _save_history(user_id: str, history: list[dict]):
    r = await _get_redis()
    # Зберігаємо останні 20 повідомлень (10 пар user/model)
    trimmed = history[-20:]
    await r.set(f"chat:{user_id}", json.dumps(trimmed, ensure_ascii=False), ex=86400)

async def _clear_history(user_id: str):
    r = await _get_redis()
    await r.delete(f"chat:{user_id}")

# ── Виклик інструменту ────────────────────────────────────────────────────────
async def _execute_tool(tool_name: str, args: dict, user_id: str) -> str:
    if tool_name == "get_weather":
        city = args.get("city", "")
        weather = await fetch_full_weather(city, WEATHER_API_KEY)
        if "error" in weather:
            return weather["error"]
        # Зберігаємо місто для /last_city та daily-нотифікацій
        r = await _get_redis()
        await r.set(f"city:{user_id}", city)
        return json.dumps(weather, ensure_ascii=False)
    return "Інструмент не знайдено."

# ── Головна функція агента ────────────────────────────────────────────────────
async def process_message(user_id: str, user_text: str) -> str:
    """
    Обробляє повідомлення користувача через Gemini.
    Повертає текстову відповідь бота.
    """
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=SYSTEM_PROMPT,
        tools=TOOLS,
    )

    history = await _load_history(user_id)

    # Додаємо нове повідомлення
    history.append({"role": "user", "parts": [user_text]})

    # Перетворюємо history у формат Gemini
    chat = model.start_chat(history=history[:-1])  # history без останнього (ми передамо його як prompt)

    response = await chat.send_message_async(user_text)

    # Aгентний цикл: Gemini може кілька разів викликати tools
    max_iterations = 5
    for _ in range(max_iterations):
        # Перевіряємо чи є function calls
        has_tool_call = False
        tool_results = []

        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call.name:
                has_tool_call = True
                fn = part.function_call
                tool_result = await _execute_tool(
                    fn.name,
                    dict(fn.args),
                    user_id
                )
                tool_results.append({
                    "function_response": {
                        "name": fn.name,
                        "response": {"result": tool_result},
                    }
                })

        if not has_tool_call:
            break

        # Відправляємо результати tools назад у Gemini
        response = await chat.send_message_async(tool_results)

    # Отримуємо фінальний текст
    final_text = response.text.strip() if response.text else "Вибач, не вдалось отримати відповідь 😔"

    # Зберігаємо діалог у Redis
    history.append({"role": "model", "parts": [final_text]})
    await _save_history(user_id, history)

    return final_text

async def reset_chat(user_id: str):
    """Скидає історію діалогу для користувача."""
    await _clear_history(user_id)
