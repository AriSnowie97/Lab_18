#!/bin/bash
# Запускаємо FastAPI у фоновому режимі (&)
python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} &

# Запускаємо Telegram-бота
python weather_bot.py
