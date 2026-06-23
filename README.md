# 🌤️ Telegram Weather Bot

Telegram-бот для перегляду актуальної погоди по назві міста. Побудований на Python + aiogram, з постійним зберіганням через Redis та хостингом на Railway.

## ✨ Можливості

- `/start` — Привітання та інструкція
- `/weather <місто>` — Погода в будь-якому місті
- `/last_city` — Останнє запитане місто (зберігається в Redis)
- `/help` — Список команд
- `/info` — Інформація про бота
- Просто надіслати назву міста — теж працює!

## 🛠️ Технічний стек

| Компонент | Технологія |
|-----------|-----------|
| Мова | Python 3.11+ |
| Telegram API | aiogram 3.x |
| HTTP-запити | aiohttp |
| Зберігання даних | Redis |
| Хостинг | Railway |
| Погодний API | OpenWeatherMap |

## 🚀 Деплой на Railway

1. Форкни цей репозиторій
2. Зайди на [railway.app](https://railway.app) і створи новий проект з GitHub
3. Додай плагін **Redis** у проект (Railway → New → Database → Redis)
4. У розділі **Variables** додай:
   ```
   BOT_TOKEN=твій_токен_від_BotFather
   WEATHER_API_KEY=твій_ключ_від_openweathermap.org
   ```
   > `REDIS_URL` Railway підставить автоматично після додавання Redis-плагіна
5. Railway задеплоїть бота автоматично при кожному `git push`

## 🔧 Локальний запуск

```bash
# Клонуй репозиторій
git clone https://github.com/YOUR_USERNAME/telegram-weather-bot.git
cd telegram-weather-bot

# Встанови залежності
pip install -r requirements.txt

# Скопіюй .env.example і заповни токени
cp .env.example .env

# Запусти Redis локально (або використай Docker)
docker run -d -p 6379:6379 redis

# Запусти бота
python weather_bot.py
```

## 📦 Структура проекту

```
telegram-weather-bot/
├── weather_bot.py      # Основний код бота
├── requirements.txt    # Python-залежності
├── Procfile            # Інструкція для Railway
├── .env.example        # Шаблон змінних середовища
├── .gitignore
└── README.md
```

## 🔑 Отримання ключів

- **BOT_TOKEN**: [@BotFather](https://t.me/BotFather) в Telegram → `/newbot`
- **WEATHER_API_KEY**: Реєстрація на [openweathermap.org](https://openweathermap.org/api) → Free plan

## 📄 Ліцензія

MIT
