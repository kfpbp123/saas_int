import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pyrogram import Client, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Путь к основному боту
MAIN_BOT_PATH = r"D:\TG_Bots\mine_bot_tg-main\mine_bot_tg-main\mine_bot_tg-main"
sys.path.append(MAIN_BOT_PATH)

import config

# Загрузка переменных окружения
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TARGET_BOT = "tgreplay_bot" # Юзернейм основного бота без @

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

async def auto_scan_and_post():
    """Сканирует каналы и ПЕРЕСЫЛАЕТ моды основному боту для корректной регистрации file_id."""
    print(f"[{datetime.now()}] Старт авто-сканирования (МЕТОД ПЕРЕСЫЛКИ)...")
    mods_found = 0
    
    async for dialog in app.get_dialogs():
        if mods_found >= AUTO_POST_LIMIT:
            break
            
        username = (dialog.chat.username or "").lower()
        invite_link = (dialog.chat.invite_link or "").lower()

        # Проверка белого списка
        is_whitelisted = any(t.lower() in username or t.lower() in invite_link for t in WHITELIST_CHANNELS)
        if dialog.chat.type.value != "channel" or not is_whitelisted or any(ex in username for ex in EXCLUDED_CHANNELS):
            continue

        print(f"🔎 Сканирую: @{username or 'Private'}")
        
        messages = []
        async for m in app.get_chat_history(dialog.chat.id, limit=30):
            messages.append(m)
        
        for i in range(len(messages)):
            if mods_found >= AUTO_POST_LIMIT: break
            
            msg = messages[i]
            if (msg.document or msg.video) and (msg.date > datetime.now() - timedelta(days=2)):
                # Проверяем, не пересылали ли мы это уже (пока упрощенно)
                try:
                    # Пересылаем сначала картинку/описание (если есть выше)
                    if i + 1 < len(messages):
                        companion = messages[i+1]
                        if abs((msg.date - companion.date).total_seconds()) < 120 and (companion.photo or companion.text):
                            await companion.forward(TARGET_BOT)
                            await asyncio.sleep(1)
                    
                    # Пересылаем сам файл
                    await msg.forward(TARGET_BOT)
                    mods_found += 1
                    print(f"✅ Переслан мод {mods_found}/{AUTO_POST_LIMIT}")
                    await asyncio.sleep(5)
                except Exception as e:
                    print(f"❌ Ошибка пересылки: {e}")

    print(f"Финиш: Переслано {mods_found} модов.")

@app.on_message(filters.me & filters.command("scan", prefixes="."))
async def manual_scan(client, message):
    await message.edit_text("⏳ Запуск сканирования и ПЕРЕСЫЛКИ модов...")
    await auto_scan_and_post()
    await message.delete()

@app.on_message(filters.me & filters.command("test", prefixes="."))
async def manual_test(client, message):
    await message.edit_text("🧪 Тест: Пересылаю 1 мод основному боту...")
    global AUTO_POST_LIMIT
    old = AUTO_POST_LIMIT
    AUTO_POST_LIMIT = 1
    await auto_scan_and_post()
    AUTO_POST_LIMIT = old
    await asyncio.sleep(3)
    await message.delete()

async def main():
    print("🚀 Запуск юзербота (Bridge Mode)...")
    await app.start()
    scheduler.add_job(auto_scan_and_post, "interval", hours=24, next_run_time=datetime.now() + timedelta(minutes=1))
    scheduler.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt: pass
    finally: app.stop()
