# weather_api.py
import aiohttp

async def get_current_weather(city: str, api_key: str) -> dict:
    """Отримує поточну погоду по назві міста. Повертає сирі дані OWM."""
    url = (
        f"http://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={api_key}&units=metric&lang=uk"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

async def get_uv_index(lat: float, lon: float, api_key: str) -> float | None:
    """Отримує УФ-індекс за координатами."""
    url = (
        f"http://api.openweathermap.org/data/2.5/uvi"
        f"?lat={lat}&lon={lon}&appid={api_key}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data.get("value")

def uv_description(uv: float | None) -> str:
    """Повертає опис УФ-індексу."""
    if uv is None:
        return "немає даних"
    if uv < 3:
        return f"{uv:.1f} 🟢 Низький"
    elif uv < 6:
        return f"{uv:.1f} 🟡 Помірний"
    elif uv < 8:
        return f"{uv:.1f} 🟠 Високий — використовуй сонцезахист"
    elif uv < 11:
        return f"{uv:.1f} 🔴 Дуже високий — мінімізуй перебування на сонці"
    else:
        return f"{uv:.1f} 🟣 Екстремальний — залишайся в тіні"

def get_wind_direction(degrees: float | None) -> str:
    if degrees is None:
        return "не визначено"
    directions = ["Пн", "Пн-Сх", "Сх", "Пд-Сх", "Пд", "Пд-Зх", "Зх", "Пн-Зх"]
    return directions[round(degrees / 45) % 8]

async def fetch_full_weather(city: str, api_key: str) -> dict:
    """
    Повертає повний набір даних про погоду включно з УФ-індексом.
    Зручно передавати в Gemini як контекст.
    """
    data = await get_current_weather(city, api_key)
    if data.get("cod") != 200:
        return {"error": f"Місто '{city}' не знайдено. Перевірте написання."}

    main = data["main"]
    weather = data["weather"][0]
    wind = data["wind"]
    lat = data["coord"]["lat"]
    lon = data["coord"]["lon"]

    uv = await get_uv_index(lat, lon, api_key)

    return {
        "city": data["name"],
        "country": data["sys"]["country"],
        "lat": lat,
        "lon": lon,
        "temp": main["temp"],
        "feels_like": main["feels_like"],
        "temp_min": main["temp_min"],
        "temp_max": main["temp_max"],
        "description": weather["description"],
        "humidity": main["humidity"],
        "pressure": main["pressure"],
        "wind_speed": wind["speed"],
        "wind_direction": get_wind_direction(wind.get("deg")),
        "visibility": data.get("visibility", "немає даних"),
        "uv_index": uv,
        "uv_description": uv_description(uv),
        "clouds": data.get("clouds", {}).get("all", 0),
    }

def format_weather_card(w: dict) -> str:
    """Форматує погоду у вигляді картки для Telegram (Markdown)."""
    return (
        f"📍 *{w['city']}, {w['country']}*\n\n"
        f"🌡️ Температура: *{w['temp']}°C* (відчувається як {w['feels_like']}°C)\n"
        f"🔻 Мін: {w['temp_min']}°C  🔺 Макс: {w['temp_max']}°C\n"
        f"☁️ {w['description'].capitalize()}\n"
        f"💧 Вологість: {w['humidity']}%\n"
        f"💨 Вітер: {w['wind_speed']} м/с, {w['wind_direction']}\n"
        f"🔽 Тиск: {w['pressure']} hPa\n"
        f"👁️ Видимість: {w['visibility']} м\n"
        f"☀️ УФ-індекс: {w['uv_description']}"
    )
