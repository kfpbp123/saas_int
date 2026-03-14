import asyncio
import os
import sys
import time
import sqlite3
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
EXCLUDED_CHANNELS = ["lazikosmods", "lab_mine", "AstralUZmods"]
AD_KEYWORDS = ["реклама", "priz", "konkurs", "game", "o'yin", "pul", "money", "tg_app"] # Черный список слов

WHITELIST_CHANNELS = [
    "minecraft_modyy", 
    "InfinitMinecraft",
    "I7QhTxE2OcxlZWQy", 
    "v6PY3UuUQndhYzg6",
    "Ix-HoEUPSAU2YzQy"
]
DEFAULT_LANG = "uz" 
AUTO_POST_LIMIT = 6 

app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH)
scheduler = AsyncIOScheduler()

def get_next_schedule_time():
    """Рассчитывает время для следующего поста в умной очереди (+8 часов от последнего)."""
    try:
        last_time = database.get_last_scheduled_time()
        interval = getattr(config, 'SMART_QUEUE_INTERVAL_HOURS', 8)
        
        if not last_time or last_time < int(time.time()):
            return int(time.time()) + 3600 # Через час, если очередь пуста
        
        return last_time + (interval * 3600)
    except Exception as e:
        print(f"⚠️ Ошибка при расчете времени: {e}")
        return int(time.time()) + 3600

def is_duplicate(doc_id):
    """Проверяет, есть ли такой файл уже в базе данных."""
    if not doc_id: return False
    try:
        conn = sqlite3.connect(database.DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM queue WHERE document_id = ?", (doc_id,))
        res = c.fetchone()
        conn.close()
        return res is not None
    except:
        return False

def is_target_channel(chat):
    """Проверяет, входит ли канал в строго заданный белый список."""
    username = (chat.username or "").lower()
    invite_link = (chat.invite_link or "").lower()
    
    # Сначала проверяем, не наш ли это канал
    if any(ex.lower() in username for ex in EXCLUDED_CHANNELS):
        return False

    # Проверка по белому списку
    if any(target.lower() in username or target.lower() in invite_link for target in WHITELIST_CHANNELS):
        return True
    return False

async def process_and_queue_mod(message, channel_username):
    """Обрабатывает сообщение, генерирует пост и кладет в базу данных основного бота."""
    try:
        # СТРОГОЕ УСЛОВИЕ: Должен быть файл (мод)
        if not (message.document or message.video):
            return False

        # ПРОВЕРКА НА РЕКЛАМУ ПО КЛЮЧЕВЫМ СЛОВАМ
        raw_text = (message.text or message.caption or "").lower()
        if any(ad in raw_text for ad in AD_KEYWORDS):
            print(f"⏩ Пропуск: Пост из @{channel_username} похож на рекламу.")
            return False

        doc_id = message.document.file_id if message.document else message.video.file_id
        file_name = message.document.file_name if message.document else "mod_file"
        
        # Проверяем на дубликат по файлу
        if is_duplicate(doc_id):
            print(f"⏩ Пропуск: файл из @{channel_username} уже в базе.")
            return False

        # Формируем расширенный ввод для ИИ (текст + имя файла)
        ai_input = f"Fayl nomi: {file_name}\nMatn: {raw_text}"
        
        # 1. Генерируем текст в стиле основного бота
        ai_text = ai_generator.generate_post(ai_input, DEFAULT_LANG)
        
        # ЕСЛИ ИИ ОТКЛОНИЛ ПОСТ (REJECT)
        if "REJECT" in ai_text.upper():
            print(f"⏩ Пропуск: ИИ определил пост из @{channel_username} как мусор/рекламу.")
            return False
            
        # 2. Собираем медиа
        photo_id = message.photo.file_id if message.photo else None
            
        # 3. Рассчитываем время публикации
        scheduled_time = get_next_schedule_time()
        
        # 4. Сохраняем напрямую в БД основного бота
        database.add_to_queue(
            photo_id=photo_id,
            text=ai_text,
            document_id=doc_id,
            channel_id=config.DEFAULT_CHANNEL,
            scheduled_time=scheduled_time
        )
        
        # 5. Уведомление в Избранное
        readable_time = datetime.fromtimestamp(scheduled_time).strftime('%d.%m %H:%M')
        report = (
            f"🤖 **Авто-постинг: Новый мод!**\n\n"
            f"📁 **Источник:** @{channel_username}\n"
            f"📅 **Дата публикации:** `{readable_time}`\n"
            f"✅ **Статус:** Добавлено в очередь."
        )
        await app.send_message("me", report)
        return True
    except Exception as e:
        print(f"❌ Ошибка при обработке мода: {e}")
        return False

async def auto_scan_and_post():
    """Раз в 24 часа ищет 6 новых модов и ставит их в очередь."""
    print(f"[{datetime.now()}] Старт авто-сканирования (СТРОГИЙ ФИЛЬТР)...")
    mods_found = 0
    
    async for dialog in app.get_dialogs():
        if mods_found >= AUTO_POST_LIMIT:
            break
            
        if dialog.chat.type.value == "channel" and is_target_channel(dialog.chat):
            username = dialog.chat.username or "Private_Channel"
            print(f"🔎 Сканирую: @{username}")
            
            # Ищем свежие посты за последние 48 часов
            async for message in app.get_chat_history(dialog.chat.id, limit=30):
                if mods_found >= AUTO_POST_LIMIT:
                    break
                
                # Нам нужны ТОЛЬКО посты с документами (файлами)
                if (message.document or message.video) and (message.date > datetime.now() - timedelta(days=2)):
                    success = await process_and_queue_mod(message, username)
                    if success:
                        mods_found += 1
                        await asyncio.sleep(5) 
    
    print(f"Финиш: Добавлено {mods_found} новых модов.")

@app.on_message(filters.me & filters.command("scan", prefixes="."))
async def manual_scan(client, message):
    await message.edit_text("⏳ Запуск ручного сканирования каналов...")
    await auto_scan_and_post()
    await message.delete()

@app.on_message(filters.me & filters.command("test", prefixes="."))
async def manual_test(client, message):
    """Тестовый запуск: ищет ровно 1 мод в белом списке и создает пост."""
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
        # Возвращаем лимит на место
        AUTO_POST_LIMIT = old_limit
        await asyncio.sleep(3)
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
