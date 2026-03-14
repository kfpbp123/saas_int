import subprocess
import time
import sys

def run_bot(script_name):
    """Запускает процесс бота и возвращает объект процесса."""
    return subprocess.Popen([sys.executable, script_name])

if __name__ == "__main__":
    print("🚀 Запуск объединенной системы ботов...")
    
    # 1. Запуск основного бота (Telebot)
    main_bot = run_bot("main.py")
    print("✅ Основной бот (@tgreplay_bot) запущен.")
    
    # Небольшая пауза для инициализации
    time.sleep(2)
    
    # 2. Запуск юзербота (Pyrogram)
    userbot = run_bot("userbot_worker.py")
    print("✅ Юзербот запущен и начал сканирование.")

    print("\n-------------------------------------------")
    print("Система работает. Нажмите Ctrl+C для выхода.")
    print("-------------------------------------------")

    try:
        # Держим скрипт запущенным, пока работают боты
        while True:
            if main_bot.poll() is not None:
                print("⚠️ Основной бот упал! Перезапуск...")
                main_bot = run_bot("main.py")
            if userbot.poll() is not None:
                print("⚠️ Юзербот упал! Перезапуск...")
                userbot = run_bot("userbot_worker.py")
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n🛑 Завершение работы...")
        main_bot.terminate()
        userbot.terminate()
        print("Все боты остановлены.")
