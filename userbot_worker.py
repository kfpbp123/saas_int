import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pyrogram import Client, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Добавляем путь к основному боту, чтобы импортировать его модули
MAIN_BOT_PATH = r"D:\TG_Bots\mine_bot_tg-main\mine_bot_tg-main\mine_bot_tg-main"
sys.path.append(MAIN_BOT_PATH)

import ai_generator
import database
import config

# Загрузка переменных окружения
load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Настройки юзербота
EXCLUDED_CHANNELS = ["lab_mine", "AstralUZmods"]
DEFAULT_LANG = "uz" # Язык для авто-постов
AUTO_POST_LIMIT = 6 # Сколько модов искать за раз

app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH)
scheduler = AsyncIOScheduler()

def get_next_schedule_time():
    """Рассчитывает время для следующего поста в умной очереди (+8 часов от последнего)."""
    last_time = database.get_last_scheduled_time()
    interval = getattr(config, 'SMART_QUEUE_INTERVAL_HOURS', 8)
    
    if not last_time or last_time < int(time.time()):
        return int(time.time()) + 3600 # Через час, если очередь пуста
    
    return last_time + (interval * 3600)

async def process_and_queue_mod(message, channel_username):
    """Обрабатывает сообщение, генерирует пост и кладет в базу данных основного бота."""
    try:
        text = message.text or message.caption or "Minecraft Mod"
        
        # 1. Генерируем текст в стиле основного бота
        ai_text = ai_generator.generate_post(text, DEFAULT_LANG)
        
        # 2. Собираем медиа
        photo_id = None
        if message.photo:
            photo_id = message.photo.file_id
        
        document_id = None
        if message.document:
            document_id = message.document.file_id
        elif message.video:
            document_id = message.video.file_id
            
        # 3. Рассчитываем время публикации
        scheduled_time = get_next_schedule_time()
        
        # 4. Сохраняем напрямую в БД основного бота
        database.add_to_queue(
            photo_id=photo_id,
            text=ai_text,
            document_id=document_id,
            channel_id=config.DEFAULT_CHANNEL,
            scheduled_time=scheduled_time
        )
        
        # 5. Уведомление в Избранное
        readable_time = datetime.fromtimestamp(scheduled_time).strftime('%d.%m %H:%M')
        report = (
            f"🤖 **Авто-постинг: Новый мод в очереди!**\n\n"
            f"📁 **Источник:** @{channel_username}\n"
            f"📅 **Дата публикации:** `{readable_time}`\n"
            f"✅ **Статус:** Текст сгенерирован, файлы прикреплены."
        )
        await app.send_message("me", report)
        return True
    except Exception as e:
        print(f"❌ Ошибка при обработке мода: {e}")
        return False

async def auto_scan_and_post():
    """Раз в 24 часа ищет 6 новых модов и ставит их в очередь."""
    print(f"[{datetime.now()}] Старт авто-сканирования...")
    mods_found = 0
    
    async for dialog in app.get_dialogs():
        if mods_found >= AUTO_POST_LIMIT:
            break
            
        if dialog.chat.type.value == "channel":
            username = dialog.chat.username
            if not username or username in EXCLUDED_CHANNELS:
                continue
            
            # Ищем свежие посты за последние 24 часа
            async for message in app.get_chat_history(dialog.chat.id, limit=20):
                if mods_found >= AUTO_POST_LIMIT:
                    break
                
                # Нам нужны посты с файлами
                if (message.document or message.video) and (message.date > datetime.now() - timedelta(days=1)):
                    success = await process_and_queue_mod(message, username)
                    if success:
                        mods_found += 1
                        await asyncio.sleep(5) # Пауза для стабильности
    
    print(f"Финиш: Добавлено {mods_found} новых модов в очередь.")

@app.on_message(filters.me & filters.command("scan", prefixes="."))
async def manual_scan(client, message):
    await message.edit_text("⏳ Запуск ручного сканирования каналов...")
    await auto_scan_and_post()
    await message.delete()

@app.on_message(filters.me & filters.command("report", prefixes="."))
async def simple_report(client, message):
    """Старая функция краткого отчета (для удобства)"""
    await message.edit_text("Генерирую краткий отчет по новостям...")
    # ... логика репорта ...
    await message.delete()

async def main():
    """Главная функция запуска."""
    print("🚀 Запуск юзербота...")
    await app.start()
    print("✅ Юзербот авторизован и подключен.")
    
    # Добавляем задачу в планировщик после старта
    # Первый запуск через 1 минуту после старта, затем каждые 24 часа
    scheduler.add_job(auto_scan_and_post, "interval", hours=24, next_run_time=datetime.now() + timedelta(minutes=1))
    scheduler.start()
    
    print(f"База данных: {database.DB_PATH}")
    print("🤖 Юзербот готов к работе. Ожидаю команды или время сканирования...")
    
    # Держим бота запущенным
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
