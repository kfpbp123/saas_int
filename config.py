import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_IDS = [5703605946] # Твой ID администратора
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

CHANNELS_STR = os.getenv("CHANNELS", "@lazikosmods")
AVAILABLE_CHANNELS = [ch.strip() for ch in CHANNELS_STR.split(',')]
DEFAULT_CHANNEL = AVAILABLE_CHANNELS[0] if AVAILABLE_CHANNELS else ""

WATERMARK_TEXT = "@lazikosmods"

# 🧠 НОВАЯ НАСТРОЙКА: Интервал умной очереди (в часах)
SMART_QUEUE_INTERVAL_HOURS = 8