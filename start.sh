#!/bin/bash
# Запускаємо Telegram-бота у фоні
python weather_bot.py &

# Запускаємо FastAPI на передньому плані (це важливо для Railway!)
python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}

