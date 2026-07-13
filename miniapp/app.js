/* app.js — WeatherBot Mini App */
'use strict';

// ── Config ───────────────────────────────────────────────────────
// API на Railway, статика на GitHub Pages — разные домены, поэтому хардкодим
const API_BASE = 'https://weathertgbot-production.up.railway.app';

// ── Telegram WebApp init ─────────────────────────────────────────
const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  // Применяем цветовую тему Telegram если доступна
  applyTgTheme();
}

function applyTgTheme() {
  const p = tg?.themeParams;
  if (!p) return;
  // Если светлая тема — немного осветляем glass
  if (tg.colorScheme === 'light') {
    document.documentElement.style.setProperty('--glass-bg', 'rgba(255,255,255,0.18)');
  }
}

// ── User ID ──────────────────────────────────────────────────────
// В реальном Mini App берём из initDataUnsafe; в браузере — заглушка
const userId = String(
  tg?.initDataUnsafe?.user?.id ?? 'preview_user'
);

// ── Clock ────────────────────────────────────────────────────────
const headerTime = document.getElementById('header-time');
function updateClock() {
  headerTime.textContent = new Date().toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
}
updateClock();
setInterval(updateClock, 10_000);

// ── Tab Navigation ───────────────────────────────────────────────
const navBtns   = document.querySelectorAll('.nav-btn');
const tabPanels = document.querySelectorAll('.tab-panel');

navBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    navBtns.forEach(b => b.classList.toggle('active', b === btn));
    tabPanels.forEach(p => p.classList.toggle('active', p.id === `panel-${tab}`));
    if (tab === 'forecast') loadForecast();
    if (tab === 'chat')     initChat();
  });
});

// ── Toast ─────────────────────────────────────────────────────────
function showToast(msg, ms = 2400) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// ════════════════════════════════════════════════════════════════════
//  WEATHER TAB
// ════════════════════════════════════════════════════════════════════
const weatherContent  = document.getElementById('weather-content');
const cityInput       = document.getElementById('city-input');
const citySearchBtn   = document.getElementById('city-search-btn');
const gpsBtn          = document.getElementById('gps-btn');

// Remember last used params for forecast
let lastWeatherParams = null;

// Load weather on start via GPS
window.addEventListener('load', () => { fetchWeatherGPS(true); });

citySearchBtn.addEventListener('click', () => {
  const city = cityInput.value.trim();
  if (city) fetchWeatherByCity(city);
});
cityInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); citySearchBtn.click(); }
});
gpsBtn.addEventListener('click', () => fetchWeatherGPS(false));

function fetchWeatherGPS(silent = false) {
  if (!navigator.geolocation) {
    if (!silent) showToast('⚠️ Геолокація не підтримується');
    return;
  }
  gpsBtn.classList.add('loading');
  gpsBtn.textContent = '⏳ Визначаю...';

  navigator.geolocation.getCurrentPosition(
    async pos => {
      const { latitude: lat, longitude: lon } = pos.coords;
      lastWeatherParams = { lat, lon };
      await fetchWeather({ lat, lon });
      gpsBtn.classList.remove('loading');
      gpsBtn.innerHTML = '<span>📍</span> Визначити за GPS';
    },
    err => {
      gpsBtn.classList.remove('loading');
      gpsBtn.innerHTML = '<span>📍</span> Визначити за GPS';
      if (!silent) showToast('📍 Не вдалось отримати GPS');
    },
    { timeout: 8000, enableHighAccuracy: true }
  );
}

async function fetchWeatherByCity(city) {
  lastWeatherParams = { city };
  await fetchWeather({ city });
}

async function fetchWeather(params) {
  weatherContent.innerHTML = '<div class="spinner"></div>';
  try {
    const qs = new URLSearchParams({ ...params, user_id: userId });
    const res = await fetch(`${API_BASE}/api/weather?${qs}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? 'Місто не знайдено');
    }
    const w = await res.json();
    renderWeather(w);
  } catch (e) {
    weatherContent.innerHTML = `
      <div class="glass" style="padding:24px;text-align:center;color:var(--text-muted)">
        ⚠️ ${e.message}
      </div>`;
  }
}

function getWeatherBg(icon) {
  // Day vs night, weather condition
  const id = icon || '01d';
  if (id.startsWith('01')) return 'linear-gradient(145deg,#1e3a8a,#0ea5e9)'; // clear
  if (id.startsWith('02') || id.startsWith('03') || id.startsWith('04'))
    return 'linear-gradient(145deg,#1e293b,#334155)';
  if (id.startsWith('09') || id.startsWith('10'))
    return 'linear-gradient(145deg,#1e3a5f,#0369a1)';
  if (id.startsWith('11'))
    return 'linear-gradient(145deg,#1e1b4b,#4338ca)';
  if (id.startsWith('13'))
    return 'linear-gradient(145deg,#1e3a5f,#7dd3fc)';
  return 'linear-gradient(145deg,#1a0533,#0d1b3e)';
}

function renderWeather(w) {
  const iconUrl = `https://openweathermap.org/img/wn/${w.icon ?? '01d'}@2x.png`;
  const bg = getWeatherBg(w.icon);

  weatherContent.innerHTML = `
    <div class="glass weather-main-card" style="background:${bg.replace('linear-gradient','linear-gradient').replace('145deg','145deg')};border-color:rgba(255,255,255,0.12)">
      <img class="weather-icon-img" src="${iconUrl}" alt="${w.description}" onerror="this.style.fontSize='64px';this.src='';this.alt='🌤️'"/>
      <div class="weather-location">📍 ${w.city}, ${w.country}</div>
      <div class="weather-temp">${Math.round(w.temp)}°</div>
      <div class="weather-desc">${w.description}</div>
      <div class="weather-minmax">↓ ${Math.round(w.temp_min)}° / ↑ ${Math.round(w.temp_max)}°</div>
      <div class="weather-feels">Відчувається як ${Math.round(w.feels_like)}°</div>
    </div>

    <div class="weather-details">
      ${detailCard('💧', `${w.humidity}%`, 'Вологість')}
      ${detailCard('💨', `${w.wind_speed} м/с`, 'Вітер')}
      ${detailCard('🔽', `${w.pressure}`, 'Тиск, гПа')}
      ${detailCard('👁️', `${w.visibility ? Math.round(w.visibility/1000)+'км' : '—'}`, 'Видимість')}
      ${detailCard('☁️', `${w.clouds}%`, 'Хмарність')}
      ${detailCard('🧭', `${w.wind_direction}`, 'Напрямок')}
    </div>

    <div class="glass uv-card">
      <span class="uv-icon">☀️</span>
      <div class="uv-info">
        <div class="uv-title">УФ-індекс</div>
        <div class="uv-val">${w.uv_description ?? '—'}</div>
      </div>
    </div>
  `;
}

function detailCard(icon, val, lbl) {
  return `
    <div class="glass detail-card">
      <div class="detail-icon">${icon}</div>
      <div class="detail-val">${val}</div>
      <div class="detail-lbl">${lbl}</div>
    </div>`;
}

// ════════════════════════════════════════════════════════════════════
//  FORECAST TAB
// ════════════════════════════════════════════════════════════════════
const forecastContent   = document.getElementById('forecast-content');
const forecastCityLabel = document.getElementById('forecast-city-label');
let forecastLoaded      = false;

const DAY_NAMES_UK = ['Нд', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const MONTH_UK = ['січ','лют','бер','кві','тра','чер','лип','сер','вер','жов','лис','гру'];

async function loadForecast() {
  if (forecastLoaded) return;
  forecastLoaded = true;

  forecastContent.innerHTML = '<div class="spinner"></div>';

  // Use same params as current weather (GPS or city)
  // If nothing yet — try GPS first, then fallback to Kyiv
  let params = lastWeatherParams;
  if (!params) {
    // try GPS silently
    params = await new Promise(resolve => {
      if (!navigator.geolocation) { resolve({ city: 'Kyiv' }); return; }
      navigator.geolocation.getCurrentPosition(
        pos => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        ()   => resolve({ city: 'Kyiv' }),
        { timeout: 5000 }
      );
    });
    lastWeatherParams = params;
  }

  try {
    const qs  = new URLSearchParams(params);
    const res = await fetch(`${API_BASE}/api/forecast?${qs}`);
    if (!res.ok) throw new Error('Не вдалось отримати прогноз');
    const data = await res.json();
    renderForecast(data.days);
  } catch (e) {
    forecastContent.innerHTML = `<div class="forecast-empty">⚠️ ${e.message}</div>`;
  }
}

function renderForecast(days) {
  if (!days || !days.length) {
    forecastContent.innerHTML = '<div class="forecast-empty">📭 Немає даних прогнозу</div>';
    return;
  }

  const todayStr = new Date().toISOString().slice(0, 10);
  if (days[0]?.city) {
    forecastCityLabel.textContent = `📍 ${days[0].city}, ${days[0].country}`;
  }

  const items = days.map((d, i) => {
    const dt      = new Date(d.date + 'T12:00:00');
    const isToday = d.date === todayStr;
    const dayName = isToday
      ? 'Сьогодні'
      : DAY_NAMES_UK[dt.getDay()];
    const dateStr = `${dt.getDate()} ${MONTH_UK[dt.getMonth()]}`;
    const iconUrl = `https://openweathermap.org/img/wn/${d.icon}@2x.png`;

    return `
      <div class="glass forecast-day${isToday ? ' today' : ''}" style="animation-delay:${i * 0.06}s">
        <img class="forecast-day-icon" src="${iconUrl}" alt="${d.description}"/>
        <div class="forecast-day-info">
          <div class="forecast-day-name">
            ${dayName}${isToday ? '<span class="forecast-today-badge">Зараз</span>' : ''}
          </div>
          <div class="forecast-day-date">${dateStr}</div>
          <div class="forecast-day-desc">${d.description}</div>
          <div class="forecast-day-extra">
            <span>💧 ${d.humidity}%</span>
            <span>💨 ${d.wind_speed} м/с</span>
          </div>
        </div>
        <div class="forecast-day-temps">
          <div class="forecast-day-temp-range">
            <span class="temp-min">${Math.round(d.temp_min)}°</span>
            <span class="temp-sep">/</span>
            <span class="temp-max">${Math.round(d.temp_max)}°</span>
          </div>
        </div>
      </div>`;
  }).join('');

  forecastContent.innerHTML = `<div class="forecast-list">${items}</div>`;
}

// ════════════════════════════════════════════════════════════════════
//  CHAT TAB
// ════════════════════════════════════════════════════════════════════
const chatMessages = document.getElementById('chat-messages');
const chatInput    = document.getElementById('chat-input');
const chatSendBtn  = document.getElementById('chat-send-btn');
const chatResetBtn = document.getElementById('chat-reset-btn');
let chatInited     = false;

function initChat() {
  if (chatInited) return;
  chatInited = true;
  appendBotMsg('👋 Привіт! Я WeatherBot 🌤️\nЗапитай про погоду в будь-якому місті — я підкажу температуру, УФ-індекс, чи варто брати парасольку і не тільки!');
}

chatSendBtn.addEventListener('click', sendChat);
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
});
// Auto-resize textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
});

chatResetBtn.addEventListener('click', async () => {
  try {
    await fetch(`${API_BASE}/api/chat/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });
    chatMessages.innerHTML = '';
    appendBotMsg('🔄 Контекст скинуто! Починаємо з чистого аркуша.');
    showToast('🔄 Чат скинуто');
  } catch {}
});

async function sendChat() {
  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = '';
  chatInput.style.height = 'auto';

  appendUserMsg(text);
  const typingEl = appendTyping();
  scrollChat();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, message: text }),
    });
    const data = res.ok ? await res.json() : { reply: '⚠️ Помилка сервера' };
    typingEl.remove();
    appendBotMsg(data.reply ?? '…');
  } catch {
    typingEl.remove();
    appendBotMsg('😔 Не вдалось зв\'язатись з сервером.');
  }
  scrollChat();
}

function appendUserMsg(text) {
  const el = document.createElement('div');
  el.className = 'msg user';
  el.textContent = text;
  chatMessages.appendChild(el);
}

function appendBotMsg(text) {
  const el = document.createElement('div');
  el.className = 'msg bot';
  // Support markdown-style bold (*text*)
  el.innerHTML = text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*(.*?)\*/g,'<strong>$1</strong>')
    .replace(/\n/g,'<br>');
  chatMessages.appendChild(el);
  return el;
}

function appendTyping() {
  const el = document.createElement('div');
  el.className = 'msg bot typing';
  chatMessages.appendChild(el);
  return el;
}

function scrollChat() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}
