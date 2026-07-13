# weather_bot.py
import asyncio
import logging
import os
import traceback

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from ai_agent import process_message, reset_chat
from weather_api import fetch_full_weather, format_weather_card
from scheduler import setup_scheduler, subscribe_user, unsubscribe_user, get_subscription

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ── /start ────────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    miniapp_url = os.getenv("MINIAPP_URL", "")
    kb = None
    if miniapp_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌤️ Відкрити WeatherApp", web_app=types.WebAppInfo(url=miniapp_url))]
        ])
    await message.reply(
        "👋 Привіт! Я *WeatherBot* — твій AI-асистент з погоди 🌤️\n\n"
        "Просто напиши мені будь-що про погоду, наприклад:\n"
        "• *яка погода в Києві?*\n"
        "• *чи варто брати парасольку?*\n"
        "• *який УФ-індекс у Львові?*\n\n"
        "Або відкрий Mini App 👇 — GPS, звіти і AI-чат в одному місці!\n"
        "Або використовуй команди — /help",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ── /help ─────────────────────────────────────────────────────────────────────
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    miniapp_url = os.getenv("MINIAPP_URL", "")
    kb = None
    if miniapp_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌤️ Відкрити WeatherApp", web_app=types.WebAppInfo(url=miniapp_url))]
        ])
    await message.reply(
        "🧾 *Доступні команди:*\n\n"
        "✅ /start – Запуск бота\n"
        "ℹ️ /info – Про бота\n"
        "🌤️ /weather <місто> – Погода в конкретному місті\n"
        "📍 /last\\_city – Твоє останнє запитане місто\n"
        "🗓️ /daily <HH:MM> – Щоденне зведення о вказаному часі\n"
        "🚫 /daily off – Скасувати щоденне зведення\n"
        "🔄 /reset – Скинути контекст розмови з AI\n\n"
        "✍️ Або просто напиши запитання про погоду — AI все розуміє!\n"
        "📱 Або відкрий Mini App 👇 — GPS, звіти, AI-чат!",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ── /info ─────────────────────────────────────────────────────────────────────
@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    await message.reply(
        "🤖 *WeatherBot з AI-агентом*\n\n"
        "📡 Погодні дані: OpenWeatherMap\n"
        "🧠 AI: Google Gemini 2.0 Flash\n"
        "💾 Пам'ять: Redis\n"
        "💻 Python + aiogram 3\n"
        "🚀 Хостинг: Railway",
        parse_mode="Markdown"
    )

# ── /weather <місто> ──────────────────────────────────────────────────────────
@dp.message(Command("weather"))
async def cmd_weather(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("🌇 Введіть місто: /weather <місто>")
        return

    city = args[1]
    wait_msg = await message.reply("⏳ Отримую дані...")
    api_key = os.getenv("WEATHER_API_KEY")
    weather = await fetch_full_weather(city, api_key)

    if "error" in weather:
        await wait_msg.edit_text(f"⚠️ {weather['error']}")
        return

    text = format_weather_card(weather)
    await wait_msg.edit_text(text, parse_mode="Markdown")

# ── /last_city ────────────────────────────────────────────────────────────────
@dp.message(Command("last_city"))
async def cmd_last_city(message: types.Message):
    import redis.asyncio as aioredis
    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    city = await r.get(f"city:{message.from_user.id}")
    if city:
        await message.reply(f"📍 Твоє останнє місто: *{city}*", parse_mode="Markdown")
    else:
        await message.reply("❌ Ти ще не шукав погоду для жодного міста.")

# ── /daily ────────────────────────────────────────────────────────────────────
@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    args = message.text.split(maxsplit=1)
    user_id = str(message.from_user.id)

    if len(args) < 2:
        sub = await get_subscription(user_id)
        if sub:
            await message.reply(
                f"🗓️ Ти підписаний на щоденне зведення о *{sub['hour']:02d}:{sub['minute']:02d}*\n"
                f"Щоб скасувати: /daily off",
                parse_mode="Markdown"
            )
        else:
            await message.reply(
                "🗓️ Щоб підписатись на щоденне зведення погоди:\n"
                "`/daily 08:00`",
                parse_mode="Markdown"
            )
        return

    arg = args[1].strip()

    if arg.lower() == "off":
        await unsubscribe_user(user_id)
        await message.reply("🚫 Щоденне зведення скасовано.")
        return

    ok = await subscribe_user(user_id, arg)
    if ok:
        await message.reply(
            f"✅ Щоденне зведення погоди налаштовано на *{arg}*!\n"
            f"Переконайся що у мене є збережене місто — надішли назву міста або /weather <місто>",
            parse_mode="Markdown"
        )
    else:
        await message.reply("⚠️ Невірний формат часу. Використовуй: `/daily 08:30`", parse_mode="Markdown")

# ── /reset ────────────────────────────────────────────────────────────────────
@dp.message(Command("reset"))
async def cmd_reset(message: types.Message):
    await reset_chat(str(message.from_user.id))
    await message.reply("🔄 Контекст розмови скинуто. Починаємо з чистого аркуша!")


# ── Геолокація від користувача ───────────────────────────────────────────────
@dp.message(F.location)
async def handle_location(message: types.Message):
    """Зберігає GPS і повертає погоду для цього місця."""
    import redis.asyncio as aioredis
    from weather_api import fetch_weather_by_coords

    lat = message.location.latitude
    lon = message.location.longitude
    user_id = str(message.from_user.id)

    r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    await r.set(f"gps:{user_id}", f"{lat},{lon}")

    wait_msg = await message.reply("📍 Визначаю погоду за твоїм місцезнаходженням...")
    api_key = os.getenv("WEATHER_API_KEY")
    weather = await fetch_weather_by_coords(lat, lon, api_key)

    if "error" in weather:
        await wait_msg.edit_text(f"⚠️ {weather['error']}")
        return

    await r.set(f"city:{user_id}", weather["city"])
    await wait_msg.edit_text(format_weather_card(weather), parse_mode="Markdown")


async def _safe_edit(wait_msg, text: str, original_message):

    """Редагує wait_msg з Markdown. Якщо Telegram відхилить — шле plain text."""
    # 1) Спробуємо edit з Markdown
    try:
        await wait_msg.edit_text(text, parse_mode="Markdown")
        return
    except Exception as e:
        if "can't parse entities" not in str(e) and "parse" not in str(e).lower():
            # Повідомлення видалено або інша некритична помилка → fallback reply
            try:
                await original_message.reply(text, parse_mode="Markdown")
                return
            except Exception:
                pass

    # 2) Markdown зламаний — пробуємо edit без форматування
    try:
        await wait_msg.edit_text(text)
        return
    except Exception:
        pass

    # 3) Крайній fallback: звичайна відповідь без форматування
    try:
        await original_message.reply(text)
    except Exception:
        pass


# ── Всі інші повідомлення → AI агент ─────────────────────────────────────────
@dp.message()
async def handle_text(message: types.Message):
    user_id = str(message.from_user.id)
    user_text = message.text.strip()

    # Надсилаємо повідомлення-заглушку одразу — користувач бачить реакцію миттєво
    wait_msg = await message.reply("✍️ Печатає...")

    # Фонова задача: оновлює "typing" кожні 4 сек поки AI думає
    # (Telegram скидає індикатор через ~5 сек, тому оновлюємо частіше)
    stop_typing = asyncio.Event()

    async def keep_typing():
        while not stop_typing.is_set():
            try:
                await bot.send_chat_action(message.chat.id, "typing")
            except Exception:
                pass
            try:
                await asyncio.wait_for(asyncio.shield(stop_typing.wait()), timeout=4)
            except asyncio.TimeoutError:
                pass

    typing_task = asyncio.create_task(keep_typing())

    try:
        reply = await process_message(user_id, user_text)
    except RuntimeError as e:
        reply = str(e)
    except Exception as e:
        logger.error(f"AI agent error for user {user_id}: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        reply = f"😔 Помилка AI: `{type(e).__name__}`. Перевір Railway Logs."
    finally:
        stop_typing.set()
        typing_task.cancel()

    # Замінюємо заглушку реальною відповіддю (без зайвого повідомлення)
    await _safe_edit(wait_msg, reply, message)

# ── Запуск ────────────────────────────────────────────────────────────────────
async def main():
    scheduler = setup_scheduler(bot)
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
