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
        "icon": weather["icon"],
        "humidity": main["humidity"],
        "pressure": main["pressure"],
        "wind_speed": wind["speed"],
        "wind_direction": get_wind_direction(wind.get("deg")),
        "visibility": data.get("visibility", 0),
        "uv_index": uv,
        "uv_description": uv_description(uv),
        "clouds": data.get("clouds", {}).get("all", 0),
    }

async def fetch_weather_by_coords(lat: float, lon: float, api_key: str) -> dict:
    """
    Повертає повний набір даних про погоду за GPS-координатами.
    Використовується Mini App для автовизначення місця.
    """
    url = (
        f"http://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=uk"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()

    if data.get("cod") != 200:
        return {"error": "Не вдалось визначити погоду за координатами."}

    main = data["main"]
    weather = data["weather"][0]
    wind = data["wind"]
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
        "icon": weather["icon"],
        "humidity": main["humidity"],
        "pressure": main["pressure"],
        "wind_speed": wind["speed"],
        "wind_direction": get_wind_direction(wind.get("deg")),
        "visibility": data.get("visibility", 0),
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

async def get_forecast(api_key: str, city: str | None = None,
                       lat: float | None = None, lon: float | None = None) -> list[dict]:
    """
    Повертає прогноз на 5 днів (безкоштовний OWM API).
    Групує тригодинні точки по днях → повертає список денних підсумків.
    """
    if lat is not None and lon is not None:
        q = f"lat={lat}&lon={lon}"
    elif city:
        q = f"q={city}"
    else:
        return []

    url = (
        f"http://api.openweathermap.org/data/2.5/forecast"
        f"?{q}&appid={api_key}&units=metric&lang=uk&cnt=40"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()

    if data.get("cod") != "200":
        return []

    city_name    = data.get("city", {}).get("name", "")
    city_country = data.get("city", {}).get("country", "")

    # Групуємо по даті (UTC date)
    days: dict[str, dict] = {}
    for item in data.get("list", []):
        date_str = item["dt_txt"][:10]   # "YYYY-MM-DD"
        if date_str not in days:
            days[date_str] = {
                "date":        date_str,
                "city":        city_name,
                "country":     city_country,
                "temps":       [],
                "descriptions": [],
                "icons":       [],
                "humidity":    [],
                "wind_speed":  [],
            }
        d = days[date_str]
        d["temps"].append(item["main"]["temp"])
        d["descriptions"].append(item["weather"][0]["description"])
        d["icons"].append(item["weather"][0]["icon"])
        d["humidity"].append(item["main"]["humidity"])
        d["wind_speed"].append(item["wind"]["speed"])

    result = []
    for date_str, d in sorted(days.items()):
        # Найбільш часта іконка (денна якщо є)
        day_icons = [ic for ic in d["icons"] if ic.endswith("d")] or d["icons"]
        from collections import Counter
        top_icon = Counter(d["icons"]).most_common(1)[0][0]
        top_desc = Counter(d["descriptions"]).most_common(1)[0][0]

        result.append({
            "date":        date_str,
            "city":        d["city"],
            "country":     d["country"],
            "temp_min":    round(min(d["temps"]), 1),
            "temp_max":    round(max(d["temps"]), 1),
            "temp_avg":    round(sum(d["temps"]) / len(d["temps"]), 1),
            "description": top_desc,
            "icon":        top_icon,
            "humidity":    round(sum(d["humidity"]) / len(d["humidity"])),
            "wind_speed":  round(sum(d["wind_speed"]) / len(d["wind_speed"]), 1),
        })

    return result
