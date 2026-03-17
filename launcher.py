import telebot
import database
import time
import threading
import os
import sys

# Глобальный словарь активных инстансов ботов {bot_id: bot_object}
ACTIVE_BOTS = {}

import main 

def start_bot_instance(bot_data):
    """Запускает один конкретный инстанс бота."""
    token = bot_data.token
    print(f"🚀 Starting bot instance: @{bot_data.bot_username} (ID: {bot_data.id})")
    
    try:
        bot = telebot.TeleBot(token, threaded=True, num_threads=5)
        # Сохраняем инстанс в глобальный словарь
        ACTIVE_BOTS[bot_data.id] = bot
        
        # Регистрируем хендлеры из main.py на этот инстанс
        main.register_handlers(bot)
        
        # Запускаем поллинг
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"❌ Error in bot @{bot_data.bot_username}: {e}")

def run_launcher():
    print("🌟 MineBot SaaS Launcher Started")
    database.init_db()
    
    # 1. Запуск планировщика (Один на всех)
    import core
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

    jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')}
    scheduler = BackgroundScheduler(jobstores=jobstores)
    if not scheduler.get_job('queue_process'):
        scheduler.add_job(core.process_queue, 'interval', minutes=1, id='queue_process', replace_existing=True)
    scheduler.start()
    print("⏰ Global Scheduler started.")

    # 1.1 Запуск Web App API (FastAPI)
    try:
        from webapp.api import run_api
        api_thread = threading.Thread(target=run_api, daemon=True)
        api_thread.start()
        print("🚀 Web App API thread started.")
    except Exception as e:
        print(f"⚠️ Could not start Web App API: {e}")

    # 2. Получение и запуск ботов
    active_bots = database.get_active_bots()
    if not active_bots:
        print("⚠️ No active bots found in database.")
        import config
        if config.TELEGRAM_TOKEN:
            admin_id = config.ADMIN_IDS[0] if config.ADMIN_IDS else 0
            database.register_bot_instance(admin_id, config.TELEGRAM_TOKEN, "DefaultBot")
            active_bots = database.get_active_bots()

    threads = []
    for bot_data in active_bots:
        t = threading.Thread(target=start_bot_instance, args=(bot_data,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(1)

    print(f"✅ {len(threads)} bot instances are running.")
    
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("🛑 Shutting down launcher...")

if __name__ == "__main__":
    run_launcher()
