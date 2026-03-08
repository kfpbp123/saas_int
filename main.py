import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from apscheduler.schedulers.background import BackgroundScheduler
import time
from datetime import datetime
import os
import config
import database
import ai_generator
import watermarker

# Инициализация
database.init_db()
bot = telebot.TeleBot(config.TELEGRAM_TOKEN)

# Хранилище временных данных
user_drafts = {}
active_channels = {}

# --- ПЛАНИРОВЩИК (АВТОПОСТИНГ) ---
def check_queue():
    ready_posts = database.get_ready_posts()
    for post in ready_posts:
        post_id, photo_id, text, doc_id, channel_id = post
        try:
            if photo_id:
                bot.send_photo(channel_id, photo_id, caption=text, parse_mode="HTML")
            elif text:
                bot.send_message(channel_id, text, parse_mode="HTML")
            
            database.mark_as_posted(post_id)
            print(f"✅ Опубликовано в {channel_id}")
        except Exception as e:
            print(f"❌ Ошибка публикации: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(check_queue, 'interval', minutes=1)
scheduler.start()

# --- ОБРАБОТКА КОМАНД ---

@bot.message_handler(commands=['start'])
def start_cmd(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📝 Создать пост", "📊 Статистика")
    bot.send_message(message.chat.id, "<b>Привет!</b> Я помогу создать пост с переводом и водяным знаком.", parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📝 Создать пост")
def request_content(message):
    # Очищаем старые черновики пользователя для чистоты
    msg = bot.send_message(
        message.chat.id, 
        "<b>Ajoyib!</b> Пришлите фото мода и его описание (в одном сообщении или просто текст).",
        parse_mode="HTML"
    )
    # ПЕРЕХОД К СЛЕДУЮЩЕМУ ШАГУ
    bot.register_next_step_handler(msg, process_step_content)

def process_step_content(message):
    chat_id = message.chat.id
    input_text = message.caption if message.caption else message.text

    if not input_text:
        bot.send_message(chat_id, "❌ Ошибка: Мне нужен текст описания. Нажми кнопку создания поста еще раз.")
        return

    wait_msg = bot.send_message(chat_id, "⏳ Обрабатываю... Накладываю логотип и перевожу текст через ИИ.")

    final_photo_id = None
    
    # Обработка фото, если оно есть
    if message.photo:
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            in_p, out_p = f"in_{chat_id}.jpg", f"out_{chat_id}.jpg"
            with open(in_p, 'wb') as f: f.write(downloaded_file)
            
            # Вызов исправленного watermarker
            watermarker.add_watermark(in_p, out_p)
            
            with open(out_p, 'rb') as f:
                sent = bot.send_photo(chat_id, f, caption="📸 Фото готово!")
                final_photo_id = sent.photo[-1].file_id
            
            if os.path.exists(in_p): os.remove(in_p)
            if os.path.exists(out_p): os.remove(out_p)
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Ошибка фото: {e}")

    # Генерация текста через AI
    try:
        translated_text = ai_generator.generate_post(input_text, persona="uz")
    except Exception as e:
        print(f"AI Error: {e}")
        translated_text = f"❌ Ошибка ИИ. Оригинал:\n\n{input_text}"

    # Создание кнопок
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ В очередь", callback_data="add_to_q"),
        InlineKeyboardButton("📅 Время", callback_data="sched_exact")
    )
    markup.add(InlineKeyboardButton("🗑 Удалить", callback_data="cancel_action"))

    # Отправка результата
    res_msg = bot.send_message(chat_id, translated_text, reply_markup=markup, parse_mode="HTML")
    
    # Сохраняем данные во временный словарь
    user_drafts[res_msg.message_id] = {
        'photo': final_photo_id,
        'text': translated_text,
        'document': None,
        'channel': config.DEFAULT_CHANNEL
    }
    bot.delete_message(chat_id, wait_msg.message_id)

# --- CALLBACK ОБРАБОТЧИКИ ---

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    
    if call.data == "cancel_action":
        bot.delete_message(chat_id, call.message.message_id)
        if call.message.message_id in user_drafts:
            del user_drafts[call.message.message_id]
        return

    draft = user_drafts.get(call.message.message_id)
    if not draft:
        bot.answer_callback_query(call.id, "❌ Ошибка: Данные устарели. Создайте пост заново.")
        return

    if call.data == "add_to_q":
        database.add_to_queue(draft['photo'], draft['text'], None, draft['channel'], int(time.time()))
        bot.answer_callback_query(call.id, "✅ Добавлено в очередь!")
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)

    elif call.data == "sched_exact":
        msg = bot.send_message(chat_id, "🕒 Введи время в формате: `08.03.2026 15:30`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_scheduled_time, call.message.message_id)

def process_scheduled_time(message, draft_msg_id):
    try:
        dt = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        ts = int(dt.timestamp())
        
        draft = user_drafts.get(draft_msg_id)
        if draft:
            database.add_to_queue(draft['photo'], draft['text'], None, draft['channel'], ts)
            bot.send_message(message.chat.id, f"📅 Запланировано на {message.text}")
            bot.edit_message_reply_markup(message.chat.id, draft_msg_id, reply_markup=None)
    except:
        bot.send_message(message.chat.id, "❌ Неверный формат. Начни заново через кнопку создания поста.")

if __name__ == "__main__":
    print("🚀 Бот запущен...")
    bot.polling(none_stop=True)