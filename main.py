import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler
import time
import threading
from datetime import datetime, timedelta
import pytz
import os
import re
import html
import csv
import config
import database
import ai_generator
import watermarker
import ai_generator
import watermarker
import comments_analyzer

database.init_db()
bot = telebot.TeleBot(config.TELEGRAM_TOKEN)
user_drafts = {}
active_channels = {} 
user_personas = {} 
album_cache = {}

# --- ВИЗУАЛ И ФОРМАТИРОВАНИЕ ---
def get_time_greeting():
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    hour = datetime.now(tashkent_tz).hour
    if hour < 6: return "🌙 Доброй ночи"
    elif hour < 12: return "🌅 Доброе утро"
    elif hour < 18: return "☀️ Добрый день"
    else: return "🌆 Добрый вечер"

def format_queue_post(post, index, total):
    post_id, photo_id, text, doc_id, channel, time_sched = post
    type_icon = "🖼️" if photo_id else "📝" if not doc_id else "📁"
    if photo_id and ',' in photo_id: type_icon = "📚"
    
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    if time_sched:
        dt = datetime.fromtimestamp(time_sched, tashkent_tz)
        now = datetime.now(tashkent_tz)
        if dt.date() == now.date(): time_str = f"Сегодня в {dt.strftime('%H:%M')}"
        elif dt.date() == (now + timedelta(days=1)).date(): time_str = f"Завтра в {dt.strftime('%H:%M')}"
        else: time_str = dt.strftime('%d.%m.%Y %H:%M')
    else:
        time_str = "⏰ Не запланировано"
        
    preview = re.sub(r'<[^>]+>', '', text)[:100]
    return f"""╔═══📋 ПОСТ {index}/{total} ═══╗
{type_icon} <b>Тип:</b> {'Альбом' if photo_id and ',' in photo_id else 'Фото' if photo_id else 'Текст'}
📢 <b>Канал:</b> {channel or config.DEFAULT_CHANNEL}
⏰ <b>Время:</b> {time_str}

📝 <b>Превью:</b>
<i>{preview}{'...' if len(text) > 100 else ''}</i>
╚════════════════════╝"""

# --- РАБОТА С КАНАЛАМИ И ФАЙЛАМИ ---
def get_channels():
    channels = config.AVAILABLE_CHANNELS.copy()
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            extra_channels = [line.strip() for line in f.readlines() if line.strip()]
            for ch in extra_channels:
                if ch not in channels: channels.append(ch)
    return channels

def get_active_channel(user_id):
    ch = active_channels.get(user_id)
    if ch: return ch
    channels = get_channels()
    return channels[0] if channels else config.DEFAULT_CHANNEL

def get_active_persona(user_id):
    return user_personas.get(user_id, "uz") 

def save_ad_text(text):
    with open("ad.txt", "w", encoding="utf-8") as f: f.write(text)

def get_ad_text():
    if os.path.exists("ad.txt"):
        with open("ad.txt", "r", encoding="utf-8") as f: return f.read()
    return ""

# --- НОВАЯ ФУНКЦИЯ ЭКСПОРТА CSV ---
def export_to_csv(chat_id):
    bot.send_message(chat_id, "⏳ Выгружаю данные в таблицу Excel...")
    posts = database.get_all_posts()
    
    if not posts:
        bot.send_message(chat_id, "📭 База данных пуста, выгружать нечего.")
        return
        
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    filename = f"posts_export_{datetime.now(tashkent_tz).strftime('%Y%m%d_%H%M%S')}.csv"
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';') 
            writer.writerow(['ID', 'Канал', 'Текст поста', 'Статус', 'Время публикации', 'Наличие фото/файла'])
            
            for p in posts:
                time_str = datetime.fromtimestamp(p[6], tashkent_tz).strftime('%d.%m.%Y %H:%M') if len(p) > 6 and p[6] else "Нет"
                has_media = "Да" if p[1] or p[3] else "Нет"
                clean_text = re.sub(r'<[^>]+>', '', p[2])
                writer.writerow([p[0], p[5] if len(p) > 5 else "Default", clean_text, p[4], time_str, has_media])
                
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="📊 <b>Экспорт завершен!</b>\n\nЭтот файл можно открыть в Excel.", parse_mode="HTML")
            
        os.remove(filename)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка при выгрузке: {e}")

# --- ОЧЕРЕДЬ И ПУБЛИКАЦИЯ ---
def process_queue():
    posts = database.get_ready_posts()
    for post in posts:
        post_id, photo_id, text, document_id, channel_id = post
        target_channel = channel_id if channel_id else config.DEFAULT_CHANNEL
        publish_post_data(post_id, photo_id, text, document_id, target_channel, is_auto=True)

scheduler = BackgroundScheduler()
scheduler.add_job(process_queue, 'interval', minutes=1)
scheduler.start()

def publish_post_data(post_id, photo_id, text, document_id, channel_id, is_auto=False):
    try:
        if photo_id:
            if ',' in photo_id:
                ids = photo_id.split(',')
                media = [telebot.types.InputMediaPhoto(media=pid, caption=text if i==0 and len(text)<=1024 else None, parse_mode='HTML') for i, pid in enumerate(ids)]
                bot.send_media_group(channel_id, media)
                if len(text) > 1024:
                    bot.send_message(channel_id, text, parse_mode='HTML')
            else:
                if len(text) <= 1024:
                    bot.send_photo(channel_id, photo_id, caption=text, parse_mode='HTML')
                else:
                    bot.send_photo(channel_id, photo_id)
                    bot.send_message(channel_id, text, parse_mode='HTML')
        else:
            bot.send_message(channel_id, text, parse_mode='HTML')
            
        if document_id: bot.send_document(channel_id, document_id)
        
        if post_id != -1: 
            database.mark_as_posted(post_id)
            if is_auto:
                for admin in getattr(config, 'ADMIN_IDS', []):
                    try: bot.send_message(admin, f"✅ <b>Автопостинг:</b> Запланированный пост успешно опубликован в {channel_id}!", parse_mode='HTML')
                    except: pass
                    
        print(f"✅ Пост #{post_id} опубликован в {channel_id}!")
        return True
    except Exception as e:
        if post_id != -1 and is_auto:
            for admin in getattr(config, 'ADMIN_IDS', []):
                try: bot.send_message(admin, f"❌ <b>Ошибка автопостинга:</b> Пост не опубликован в {channel_id}. Причина: {e}", parse_mode='HTML')
                except: pass
        print(f"❌ Ошибка публикации в {channel_id}: {e}")
        return False

# --- ИНТЕРФЕЙС ОЧЕРЕДИ ---
def show_queue_page(chat_id, page, message_id=None):
    posts = database.get_all_pending()
    if not posts:
        text = "📭 Очередь пуста."
        if message_id: bot.edit_message_text(text, chat_id, message_id)
        else: bot.send_message(chat_id, text)
        return

    if page >= len(posts): page = len(posts) - 1
    if page < 0: page = 0

    msg_text = f"🕒 <b>В очереди: {len(posts)} постов</b>\n\n"
    msg_text += format_queue_post(posts[page], page + 1, len(posts))

    markup = InlineKeyboardMarkup(row_width=2)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data=f"q_page_{page-1}"))
    if page < len(posts) - 1: nav_row.append(InlineKeyboardButton("След. ➡️", callback_data=f"q_page_{page+1}"))
    if nav_row: markup.add(*nav_row)

    markup.add(
        InlineKeyboardButton("🚀 Выпустить сейчас", callback_data=f"q_pub_{posts[page][0]}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"q_del_{posts[page][0]}")
    )

    if message_id:
        try: bot.edit_message_text(msg_text, chat_id, message_id, parse_mode='HTML', reply_markup=markup)
        except Exception: pass
    else:
        bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)

def show_stats(chat_id):
    stats = database.get_stats()
    active_ch_count = len(get_channels())
    text = f"""📊 <b>СТАТИСТИКА БОТА</b> 📊

📝 Всего постов создано: <b>{stats['total']}</b>
✅ Успешно опубликовано: <b>{stats['published']}</b>
⏳ Ждут в очереди: <b>{stats['queue']}</b>
📅 Опубликовано сегодня: <b>{stats['today']}</b>
📢 Подключенных каналов: <b>{active_ch_count}</b>"""
    bot.send_message(chat_id, text, parse_mode='HTML')

# --- МЕНЮ ---
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("📝 Создать пост"))
    markup.add(KeyboardButton("🎭 Выбор стиля"), KeyboardButton("📢 Выбор канала"))
    markup.add(KeyboardButton("➕ Добавить канал"), KeyboardButton("📊 Статус очереди"))
    markup.add(KeyboardButton("📈 Статистика"), KeyboardButton("📊 Экспорт (CSV)")) 
    markup.add(KeyboardButton("💰 Реклама"), KeyboardButton("💾 Бэкап базы"))
    markup.add(KeyboardButton("💡 Запросы подписчиков"))
    return markup

def get_cancel_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(KeyboardButton("❌ Отмена"))
    return markup

def get_draft_markup(draft_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"🧠 Умная очередь (+{getattr(config, 'SMART_QUEUE_INTERVAL_HOURS', 2)} ч)", callback_data="add_to_smart_q")
    )
    markup.add(
        InlineKeyboardButton("🚀 Сейчас", callback_data="pub_now"),
        InlineKeyboardButton("📅 Позже", callback_data="pub_queue_menu")
    )
    markup.add(
        InlineKeyboardButton("✏️ Правка", callback_data="edit_text"),
        InlineKeyboardButton("✨ Переписать", callback_data="rewrite_menu")
    )
    markup.add(
        InlineKeyboardButton("💰 +Реклама", callback_data="add_ad"),
        InlineKeyboardButton("❌ Удалить", callback_data="cancel_action")
    )
    return markup

def update_draft_inline(chat_id, target_id, draft):
    markup = get_draft_markup(target_id)
    try: bot.edit_message_text(text=draft['text'], chat_id=chat_id, message_id=target_id, parse_mode='HTML', reply_markup=markup)
    except:
        try: bot.edit_message_caption(caption=draft['text'], chat_id=chat_id, message_id=target_id, parse_mode='HTML', reply_markup=markup)
        except Exception: pass

# --- ОБРАБОТЧИКИ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    greeting = get_time_greeting()
    bot.send_message(message.chat.id, f"{greeting}! Бот готов к работе.", reply_markup=get_main_menu())

@bot.message_handler(content_types=['text', 'photo'])
def handle_text_photo(message):
    if message.content_type == 'text':
        if message.text == "📝 Создать пост":
            bot.send_message(message.chat.id, "Отправь мне фото, текст или ссылку с описанием мода! 🚀", parse_mode="HTML")
            return
        elif message.text == "📊 Статус очереди": 
            show_queue_page(message.chat.id, 0)
            return
        elif message.text == "💰 Реклама":
            msg = bot.send_message(message.chat.id, f"Текущая реклама:\n{get_ad_text() or 'ПУСТО'}\n\nПришли новый текст рекламы:", parse_mode='HTML', reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_ad_step)
            return
        elif message.text == "➕ Добавить канал":
            msg = bot.send_message(message.chat.id, "Отправь @username нового канала:", reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_add_channel_step)
            return
        elif message.text == "📢 Выбор канала":
            markup = InlineKeyboardMarkup(row_width=1)
            for ch in get_channels():
                status = "✅ " if get_active_channel(message.from_user.id) == ch else ""
                markup.add(InlineKeyboardButton(f"{status}{ch}", callback_data=f"set_channel_{ch}"))
            bot.send_message(message.chat.id, "Выбери канал для публикации:", reply_markup=markup)
            return
        elif message.text == "🎭 Выбор стиля":
            markup = InlineKeyboardMarkup(row_width=1)
            active_p = get_active_persona(message.from_user.id)
            markup.add(InlineKeyboardButton(f"{'✅ ' if active_p == 'uz' else ''}🇺🇿 Узбекский", callback_data="set_persona_uz"))
            markup.add(InlineKeyboardButton(f"{'✅ ' if active_p == 'ru' else ''}🇷🇺 Русский", callback_data="set_persona_ru"))
            markup.add(InlineKeyboardButton(f"{'✅ ' if active_p == 'en' else ''}🇬🇧 Английский", callback_data="set_persona_en"))
            bot.send_message(message.chat.id, "Выбери личность бота:", reply_markup=markup)
            return
        elif message.text == "💡 Запросы подписчиков":
            msg = bot.send_message(message.chat.id, "⏳ Читаю комментарии и анализирую...")
            
            # Вызываем функцию из нашего НОВОГО файла
            report = comments_analyzer.analyze_comments()
            
            # Кнопка для очистки прочитанных комментариев
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🗑 Очистить обработанные", callback_data="clear_comments_db"))
            
            bot.delete_message(message.chat.id, msg.message_id)
            bot.send_message(message.chat.id, report, parse_mode="HTML", reply_markup=markup)
            return
        elif message.text == "📈 Статистика":
            show_stats(message.chat.id)
            return
        elif message.text == "📊 Экспорт (CSV)":
            export_to_csv(message.chat.id)
            return
        elif message.text == "💾 Бэкап базы":
            bot.send_message(message.chat.id, "Выгружаю bot_data.db...")
            if os.path.exists('bot_data.db'):
                with open('bot_data.db', 'rb') as f:
                    bot.send_document(message.chat.id, f)
            return

    if message.media_group_id:
        if message.media_group_id not in album_cache:
            album_cache[message.media_group_id] = []
            bot.send_message(message.chat.id, "📸 Загружаю альбом...")
            threading.Timer(2.0, process_album, args=[message.media_group_id, message.chat.id, message.from_user.id]).start()
        album_cache[message.media_group_id].append(message)
        return

    process_single_message(message)

def process_single_message(message):
    temp_in = f"in_{message.message_id}.jpg"
    temp_out = f"out_{message.message_id}.jpg"
    try:
        bot.send_chat_action(message.chat.id, 'upload_photo')
        
        user_input = message.caption if message.photo else message.text
        if not user_input and message.photo: user_input = "Опиши этот мод."
        elif not user_input: return
        
        persona = get_active_persona(message.from_user.id)
        generated_text = ai_generator.generate_post(user_input, persona)
        photo_id = None
        
        if message.photo:
            bot.send_message(message.chat.id, "🎨 Обрабатываю фото...")
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            with open(temp_in, 'wb') as f: f.write(downloaded_file)
            watermarker.add_watermark(temp_in, temp_out)
            target_image = temp_out if os.path.exists(temp_out) else temp_in
            
            with open(target_image, 'rb') as f:
                sent_msg = bot.send_photo(message.chat.id, f)
                photo_id = sent_msg.photo[-1].file_id
                bot.delete_message(message.chat.id, sent_msg.message_id) 
        else:
            bot.send_message(message.chat.id, "⏳ Генерирую пост...")

        draft = {'photo': photo_id, 'text': generated_text, 'document': None, 'ad_added': False, 'channel': get_active_channel(message.from_user.id)}
        send_draft_preview(message.chat.id, draft)

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")
    finally:
        if os.path.exists(temp_in): os.remove(temp_in)
        if os.path.exists(temp_out): os.remove(temp_out)

def process_album(media_group_id, chat_id, user_id):
    messages = album_cache.pop(media_group_id, None)
    if not messages: return
    messages.sort(key=lambda x: x.message_id)
    caption = next((m.caption for m in messages if m.caption), None)
    
    bot.send_message(chat_id, "🎨 Обрабатываю альбом...")
    persona = get_active_persona(user_id)
    generated_text = ai_generator.generate_post(caption or "Опиши мод", persona)
    
    temp_files = []
    opened_files = [] 
    
    try:
        for i, m in enumerate(messages):
            file_info = bot.get_file(m.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            tin, tout = f"in_{media_group_id}_{i}.jpg", f"out_{media_group_id}_{i}.jpg"
            with open(tin, 'wb') as f: f.write(downloaded_file)
            watermarker.add_watermark(tin, tout)
            target_img = tout if os.path.exists(tout) else tin
            temp_files.append((tin, target_img))
            
        media = []
        for tin, target_img in temp_files:
            f = open(target_img, 'rb')
            opened_files.append(f) 
            media.append(telebot.types.InputMediaPhoto(f))
            
        sent_msgs = bot.send_media_group(chat_id, media)
        photo_ids = [m.photo[-1].file_id for m in sent_msgs]
        photo_id_str = ",".join(photo_ids)
        
        for m in sent_msgs:
            try: bot.delete_message(chat_id, m.message_id)
            except: pass
            
        draft = {'photo': photo_id_str, 'text': generated_text, 'document': None, 'ad_added': False, 'channel': get_active_channel(user_id)}
        send_draft_preview(chat_id, draft)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка альбома: {e}")
    finally:
        for f in opened_files:
            try: f.close()
            except: pass
        for tin, tout in temp_files:
            if os.path.exists(tin): os.remove(tin)
            if os.path.exists(tout) and tout != tin: os.remove(tout)

def send_draft_preview(chat_id, draft):
    text = draft['text']
    photo_id = draft['photo']
    
    if photo_id:
        if ',' in photo_id:
            ids = photo_id.split(',')
            media = [telebot.types.InputMediaPhoto(media=pid) for pid in ids]
            bot.send_media_group(chat_id, media)
            sent = bot.send_message(chat_id, text, parse_mode='HTML')
            target_id = sent.message_id
        else:
            if len(text) <= 1024:
                sent = bot.send_photo(chat_id, photo_id, caption=text, parse_mode='HTML')
                target_id = sent.message_id
            else:
                bot.send_photo(chat_id, photo_id)
                sent = bot.send_message(chat_id, text, parse_mode='HTML')
                target_id = sent.message_id
    else:
        sent = bot.send_message(chat_id, text, parse_mode='HTML')
        target_id = sent.message_id
        
    user_drafts[target_id] = draft
    bot.edit_message_reply_markup(chat_id, target_id, reply_markup=get_draft_markup(target_id))

def process_ad_step(message):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(message.chat.id, "❌ Действие отменено.", reply_markup=get_main_menu())
        return
    save_ad_text(message.text)
    bot.send_message(message.chat.id, "✅ Реклама сохранена!", reply_markup=get_main_menu())

def process_add_channel_step(message):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=get_main_menu())
        return
    new_channel = message.text.strip()
    if not new_channel.startswith('@') and not new_channel.replace('-', '').isdigit(): new_channel = '@' + new_channel
    channels = get_channels()
    if new_channel in channels: bot.send_message(message.chat.id, f"⚠️ Канал уже есть!", reply_markup=get_main_menu())
    else:
        with open("channels.txt", "a", encoding="utf-8") as f: f.write(new_channel + "\n")
        bot.send_message(message.chat.id, f"✅ Канал добавлен!", reply_markup=get_main_menu())

def save_edited_text(message, target_id, chat_id):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(chat_id, "❌ Отменено.", reply_markup=get_main_menu())
        return
    draft = user_drafts.pop(target_id, None)
    if not draft: return
    draft['text'] = message.text
    try: bot.delete_message(chat_id, target_id)
    except: pass
    try: bot.delete_message(chat_id, message.message_id)
    except: pass
    bot.send_message(chat_id, "✅ Текст обновлен!", reply_markup=get_main_menu())
    send_draft_preview(chat_id, draft)

def process_exact_time(message, draft_id, chat_id):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(chat_id, "❌ Отменено.", reply_markup=get_main_menu())
        return
    try:
        dt_naive = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        dt_aware = tashkent_tz.localize(dt_naive)
        timestamp = int(dt_aware.timestamp())
        
        if timestamp < time.time():
            msg = bot.send_message(chat_id, "⚠️ Время прошло! Введи дату заново:", reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_exact_time, draft_id, chat_id)
            return

        draft = user_drafts.get(draft_id)
        if draft:
            database.add_to_queue(draft['photo'], draft['text'], draft['document'], draft['channel'], timestamp)
            bot.edit_message_reply_markup(chat_id, draft_id, reply_markup=None)
            bot.send_message(chat_id, f"🕒 Запланировано на {dt_naive.strftime('%d.%m.%Y %H:%M')} ({draft['channel']})", reply_markup=get_main_menu())
            del user_drafts[draft_id]
    except ValueError:
        msg = bot.send_message(chat_id, "❌ Формат: ДД.ММ.ГГГГ ЧЧ:ММ", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_exact_time, draft_id, chat_id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    target_id = call.message.message_id
    
    if call.data == "clear_comments_db":
        database.clear_comments()
        bot.answer_callback_query(call.id, "✅ База комментариев очищена!")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return
    
    if call.data == "cancel_action":
        try: bot.delete_message(chat_id, target_id)
        except: pass
        if target_id in user_drafts: del user_drafts[target_id]
        bot.answer_callback_query(call.id, "🗑 Черновик удален")
        return

    if call.data.startswith('q_'):
        parts = call.data.split('_')
        action, val = parts[1], int(parts[2])
        if action == 'page': show_queue_page(chat_id, val, target_id)
        elif action == 'del':
            database.delete_from_queue(val)
            bot.answer_callback_query(call.id, "🗑 Пост удален!")
            show_queue_page(chat_id, 0, target_id)
        elif action == 'pub':
            posts = database.get_all_pending()
            post = next((p for p in posts if p[0] == val), None)
            if post and publish_post_data(post[0], post[1], post[2], post[3], post[4] or config.DEFAULT_CHANNEL):
                bot.answer_callback_query(call.id, "🚀 Опубликовано!")
                show_queue_page(chat_id, 0, target_id)
            else: bot.answer_callback_query(call.id, "❌ Ошибка!", show_alert=True)
            return

    draft = user_drafts.get(target_id)
    if not draft and not call.data.startswith("sched_"):
        return bot.answer_callback_query(call.id, "Черновик устарел.", show_alert=True)

    if call.data == "rewrite_menu":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🤏 Короче", callback_data="rw_short"),
            InlineKeyboardButton("🤪 Веселее", callback_data="rw_fun")
        )
        markup.add(
            InlineKeyboardButton("👔 Серьезнее", callback_data="rw_pro"),
            InlineKeyboardButton("⬅️ Назад", callback_data="back_to_draft")
        )
        bot.edit_message_reply_markup(chat_id, target_id, reply_markup=markup)
        return

    if call.data.startswith("rw_"):
        style = call.data.split("_")[1]
        bot.answer_callback_query(call.id, "⏳ ИИ переписывает текст...")
        new_text = ai_generator.rewrite_post(draft['text'], style)
        draft['text'] = new_text
        update_draft_inline(chat_id, target_id, draft)
        return

    if call.data == "add_to_smart_q":
        last_time = database.get_last_scheduled_time()
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        current_time = int(datetime.now(tashkent_tz).timestamp())
        interval_seconds = getattr(config, 'SMART_QUEUE_INTERVAL_HOURS', 2) * 3600
        
        if last_time and last_time > current_time: new_time = last_time + interval_seconds
        else: new_time = current_time + interval_seconds
            
        database.add_to_queue(draft['photo'], draft['text'], draft['document'], draft['channel'], new_time)
        dt_str = datetime.fromtimestamp(new_time, tashkent_tz).strftime('%d.%m.%Y %H:%M')
        bot.answer_callback_query(call.id, "✅ Добавлено!")
        bot.edit_message_reply_markup(chat_id, target_id, reply_markup=None)
        bot.send_message(chat_id, f"🧠 Пост запланирован на {dt_str} для {draft['channel']}", parse_mode="HTML")
        del user_drafts[target_id]
        return

    if call.data == "edit_text":
        raw_text = html.escape(draft['text'])
        msg = bot.send_message(chat_id, f"✏️ <b>Скопируй код ниже:</b>\n\n<code>{raw_text}</code>", parse_mode="HTML", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, save_edited_text, target_id, chat_id)
        return

    if call.data == "add_ad":
        if draft.get('ad_added'): return bot.answer_callback_query(call.id, "Уже добавлено!", show_alert=True)
        ad_text = get_ad_text()
        if not ad_text: return bot.answer_callback_query(call.id, "Задай рекламу в меню!", show_alert=True)
        draft['text'] += f"\n\n<blockquote>{ad_text}</blockquote>"
        draft['ad_added'] = True
        update_draft_inline(chat_id, target_id, draft) 
        bot.answer_callback_query(call.id, "Добавлено!")
        return

    if call.data == "pub_now":
        if publish_post_data(-1, draft['photo'], draft['text'], draft['document'], draft['channel']):
            database.record_published_post(draft['photo'], draft['text'], draft['document'], draft['channel'])
            bot.answer_callback_query(call.id, "Опубликовано!")
            bot.edit_message_reply_markup(chat_id, target_id, reply_markup=None)
            bot.send_message(chat_id, f"🚀 Отправлено в {draft['channel']}!")
            del user_drafts[target_id]
        return

    if call.data == "pub_queue_menu":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("2 часа", callback_data=f"sched_interval_2_{target_id}"),
            InlineKeyboardButton("4 часа", callback_data=f"sched_interval_4_{target_id}"),
            InlineKeyboardButton("6 часов", callback_data=f"sched_interval_6_{target_id}"),
            InlineKeyboardButton("12 часов", callback_data=f"sched_interval_12_{target_id}"),
            InlineKeyboardButton("24 часа", callback_data=f"sched_interval_24_{target_id}")
        )
        markup.add(InlineKeyboardButton("📅 Точная дата и время", callback_data=f"sched_exact_{target_id}"))
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_draft"))
        bot.edit_message_reply_markup(chat_id, target_id, reply_markup=markup)
        return

    if call.data == "back_to_draft":
        bot.edit_message_reply_markup(chat_id, target_id, reply_markup=get_draft_markup(target_id))
        return

    if call.data.startswith("sched_interval_"):
        parts = call.data.split('_')
        hours, draft_id = int(parts[2]), int(parts[3])
        target_draft = user_drafts.get(draft_id)
        if not target_draft: return bot.answer_callback_query(call.id, "Ошибка.")
        
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        now = datetime.now(tashkent_tz)
        future = now + timedelta(hours=hours)
        timestamp = int(future.timestamp())
        
        database.add_to_queue(target_draft['photo'], target_draft['text'], target_draft['document'], target_draft['channel'], timestamp)
        bot.edit_message_reply_markup(chat_id, draft_id, reply_markup=None)
        bot.send_message(chat_id, f"🕒 Запланировано (через {hours} ч.) для {target_draft['channel']}")
        del user_drafts[draft_id]
        return

    if call.data.startswith("sched_exact_"):
        draft_id = int(call.data.split('_')[2])
        msg = bot.send_message(chat_id, "📅 Формат `ДД.ММ.ГГГГ ЧЧ:ММ`:", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_exact_time, draft_id, chat_id)
        return

@bot.message_handler(content_types=['document'])
def handle_document(message):
    if message.reply_to_message:
        target_id = message.reply_to_message.message_id
        if target_id in user_drafts:
            user_drafts[target_id]['document'] = message.document.file_id
            bot.reply_to(message, "✅ Файл прикреплен!")
            return
    bot.reply_to(message, "Сделай Reply на сообщение с кнопками!")
    
# --- СБОР КОММЕНТАРИЕВ ИЗ ГРУППЫ ---
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'], content_types=['text'])
def catch_group_comments(message):
    """Слушает сообщения в группе (комментариях) и сохраняет их в базу"""
    import time
    # Игнорируем команды ботам в группе (если они есть)
    if message.text.startswith('/'):
        return
    
    # Сохраняем имя юзера и текст комментария
    database.save_comment(message.from_user.first_name, message.text, int(time.time()))

print("Бот v15 (Умные хэштеги от Gemini) запущен!")
while True:
    try: bot.polling(none_stop=True, timeout=90)
    except Exception as e: time.sleep(5)