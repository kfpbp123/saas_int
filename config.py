import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_IDS = [5703605946] # Твой ID администратора
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Провайдер ИИ: "gemini" или "groq"
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini")

CHANNELS_STR = os.getenv("CHANNELS", "@lazikosmods")
AVAILABLE_CHANNELS = [ch.strip() for ch in CHANNELS_STR.split(',')]
DEFAULT_CHANNEL = AVAILABLE_CHANNELS[0] if AVAILABLE_CHANNELS else ""

WATERMARK_TEXT = "@lazikosmods"

# 🌐 Telegram Mini App URL (Ваш IP или домен)
_url = os.getenv("WEBAPP_URL", "")
if _url and not _url.startswith("http"):
    _url = "https://" + _url
WEBAPP_URL = _url or "http://localhost:8000"

# 🧠 НОВАЯ НАСТРОЙКА: Интервал умной очереди (в часах)
SMART_QUEUE_INTERVAL_HOURS = 6