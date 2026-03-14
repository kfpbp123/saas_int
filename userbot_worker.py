import asyncio
import os
import sys
import time
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pyrogram import Client, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Путь к основному боту
MAIN_BOT_PATH = r"D:\TG_Bots\mine_bot_tg-main\mine_bot_tg-main\mine_bot_tg-main"
sys.path.append(MAIN_BOT_PATH)

import config
import database
import core

# Загрузка переменных окружения
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TARGET_BOT = "tgreplay_bot"

# Настройки юзербота
EXCLUDED_CHANNELS = ["lazikosmods", "lab_mine", "AstralUZmods"]
WHITELIST_CHANNELS = [
    "minecraft_modyy", 
    "InfinitMinecraft",
    "I7QhTxE2OcxlZWQy", 
    "v6PY3UuUQndhYzg6",
    "Ix-HoEUPSAU2YzQy"
]
AUTO_POST_LIMIT = 6 

app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH)
scheduler = AsyncIOScheduler()

# Глобальное событие для ожидания ответа от основного бота
bot_response_event = asyncio.Event()

def init_history_db():
    """Создает локальную базу истории отправленных модов."""
    conn = sqlite3.connect("sent_history.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS sent_mods (file_unique_id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

def is_already_sent(file_unique_id):
    """Проверяет, отправляли ли мы этот мод раньше."""
    if not file_unique_id: return False
    conn = sqlite3.connect("sent_history.db")
    c = conn.cursor()
    c.execute("SELECT 1 FROM sent_mods WHERE file_unique_id = ?", (file_unique_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

def mark_as_sent(file_unique_id):
    """Записывает мод в историю навсегда."""
    if not file_unique_id: return
    conn = sqlite3.connect("sent_history.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO sent_mods VALUES (?)", (file_unique_id,))
    conn.commit()
    conn.close()

@app.on_message(filters.chat(TARGET_BOT))
async def handle_bot_reply(client, message):
    """Слушает ответы от основного бота."""
    text = (message.text or "").lower()
    if "пост добавлен" in text or "готово" in text or "отклонен" in text:
        print("📥 Получено подтверждение от основного бота.")
        bot_response_event.set()

async def auto_scan_and_post():
    """Сканирует каналы и пошагово пересылает моды с ожиданием подтверждения."""
    print(f"[{datetime.now()}] Старт авто-сканирования (SYNC MODE)...")
    init_history_db()
    mods_found = 0
    
    async for dialog in app.get_dialogs():
        if mods_found >= AUTO_POST_LIMIT: break
            
        username = (dialog.chat.username or "").lower()
        invite_link = (dialog.chat.invite_link or "").lower()

        if dialog.chat.type.value != "channel" or any(ex in username for ex in EXCLUDED_CHANNELS):
            continue
            
        if not any(t.lower() in username or t.lower() in invite_link for t in WHITELIST_CHANNELS):
            continue

        print(f"🔎 Сканирую: @{username or 'Private'}")
        
        messages = []
        async for m in app.get_chat_history(dialog.chat.id, limit=40):
            messages.append(m)
        
        for i in range(len(messages)):
            if mods_found >= AUTO_POST_LIMIT: break
            
            msg = messages[i]
            if (msg.document or msg.video) and (msg.date > datetime.now() - timedelta(days=2)):
                
                # Проверяем ГЛОБАЛЬНУЮ историю
                file_uid = msg.document.file_unique_id if msg.document else msg.video.file_unique_id
                if is_already_sent(file_uid):
                    continue

                try:
                    bot_response_event.clear() # Сбрасываем ожидание
                    
                    # 1. Пересылаем сопутствующее сообщение (фото/текст)
                    if i + 1 < len(messages):
                        companion = messages[i+1]
                        if abs((msg.date - companion.date).total_seconds()) < 120:
                            await companion.forward(TARGET_BOT)
                            await asyncio.sleep(1)
                    
                    # 2. Пересылаем сам файл
                    await msg.forward(TARGET_BOT)
                    print(f"📡 Отправлен мод {mods_found+1}. Жду подтверждения от бота...")
                    
                    # 3. ЖДЕМ ПОДТВЕРЖДЕНИЯ (таймаут 60 секунд)
                    try:
                        await asyncio.wait_for(bot_response_event.wait(), timeout=60)
                        mark_as_sent(file_uid)
                        mods_found += 1
                        print(f"✅ Мод успешно обработан.")
                    except asyncio.TimeoutError:
                        print("⚠️ Бот не ответил вовремя. Продолжаем...")
                    
                    await asyncio.sleep(5)
                except Exception as e:
                    print(f"❌ Ошибка: {e}")

    print(f"Финиш: Обработано {mods_found} модов.")

@app.on_message(filters.me & filters.command("scan", prefixes="."))
async def manual_scan(client, message):
    await message.edit_text("⏳ Запуск синхронного сканирования...")
    await auto_scan_and_post()
    await message.delete()

@app.on_message(filters.me & filters.command("test", prefixes="."))
async def manual_test(client, message):
    await message.edit_text("🧪 Тестирование: Ищу 1 свежий мод в белом списке...")
    
    # Сохраняем старый лимит и ставим 1 для теста
    global AUTO_POST_LIMIT
    old_limit = AUTO_POST_LIMIT
    AUTO_POST_LIMIT = 1
    
    try:
        await auto_scan_and_post()
        await message.edit_text("✅ Тест завершен. Проверьте очередь и Избранное.")
    except Exception as e:
        await message.edit_text(f"❌ Ошибка при тесте: {e}")
    finally:
        AUTO_POST_LIMIT = old_limit
        await asyncio.sleep(3)
        await message.delete()

@app.on_message(filters.me & filters.command("report", prefixes="."))
async def simple_report(client, message):
    """Старая функция краткого отчета (для удобства)"""
    await message.edit_text("Генерирую краткий отчет по новостям...")
    await message.delete()

async def main():
    print("🚀 Запуск юзербота (Synchronized Bridge)...")
    await app.start()
    scheduler.add_job(auto_scan_and_post, "interval", hours=24, next_run_time=datetime.now() + timedelta(minutes=1))
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt: pass
    finally: app.stop()
