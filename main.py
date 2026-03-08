import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.background import BackgroundScheduler
import time
import threading
from datetime import datetime, timedelta
import os
import re
import html
import config
import database
import ai_generator
import watermarker
import pytz

database.init_db()
bot = telebot.TeleBot(config.TELEGRAM_TOKEN)
user_drafts = {}
active_channels = {} 
user_personas = {} 
album_cache = {}

# --- РАБОТА С КАНАЛАМИ И ФАЙЛАМИ ---
def get_channels():
    """Получает каналы из .env и объединяет с добавленными вручную из channels.txt"""
    channels = config.AVAILABLE_CHANNELS.copy()
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            extra_channels = [line.strip() for line in f.readlines() if line.strip()]
            for ch in extra_channels:
                if ch not in channels:
                    channels.append(ch)
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

# --- ОЧЕРЕДЬ И ПУБЛИКАЦИЯ ---
def process_queue():
    posts = database.get_ready_posts()
    for post in posts:
        post_id, photo_id, text, document_id, channel_id = post
        target_channel = channel_id if channel_id else config.DEFAULT_CHANNEL
        publish_post_data(post_id, photo_id, text, document_id, target_channel)

scheduler = BackgroundScheduler()
scheduler.add_job(process_queue, 'interval', minutes=1)
scheduler.start()

def publish_post_data(post_id, photo_id, text, document_id, channel_id):
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
        print(f"✅ Пост #{post_id} опубликован в {channel_id}!")
        return True
    except Exception as e:
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

    post_id, photo_id, text, document_id, channel_id, scheduled_time = posts[page]

    media_info = []
    if photo_id:
        if ',' in photo_id: media_info.append(f"🖼 Альбом ({len(photo_id.split(','))} фото)")
        else: media_info.append("🖼 Фото")
    if document_id: media_info.append("📁 Файл")
    media_str = ", ".join(media_info) if media_info else "Только текст"

    clean_text = re.sub(r'<[^>]+>', '', text)
    preview_text = clean_text[:250] + "..." if len(clean_text) > 250 else clean_text
    time_str = datetime.fromtimestamp(scheduled_time).strftime('%d.%m.%Y %H:%M') if scheduled_time else "Без времени"

    msg_text = (f"🕒 <b>В очереди: {len(posts)} постов</b>\n\n"
                f"📄 <b>Пост [{page+1}/{len(posts)}]</b>\n"
                f"📢 Канал: {channel_id or config.DEFAULT_CHANNEL}\n"
                f"⏰ Запланирован: <b>{time_str}</b>\n"
                f"📎 Вложения: {media_str}\n\n"
                f"<i>{preview_text}</i>")

    markup = InlineKeyboardMarkup(row_width=2)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data=f"q_page_{page-1}"))
    if page < len(posts) - 1: nav_row.append(InlineKeyboardButton("След. ➡️", callback_data=f"q_page_{page+1}"))
    if nav_row: markup.add(*nav_row)

    markup.add(
        InlineKeyboardButton("🚀 Выпустить сейчас", callback_data=f"q_pub_{post_id}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"q_del_{post_id}")
    )

    if message_id:
        try: bot.edit_message_text(msg_text, chat_id, message_id, parse_mode='HTML', reply_markup=markup)
        except Exception: pass
    else:
        bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)

# --- ГЛАВНОЕ МЕНЮ И КНОПКИ ---
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("📝 Создать пост"))
    markup.add(KeyboardButton("🎭 Выбор стиля"), KeyboardButton("📢 Выбор канала"))
    markup.add(KeyboardButton("➕ Добавить канал"), KeyboardButton("📊 Статус очереди"))
    markup.add(KeyboardButton("💰 Реклама"))
    return markup

def get_cancel_markup():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(KeyboardButton("❌ Отмена"))
    return markup

def get_draft_markup(draft_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚀 Опубликовать сейчас", callback_data="pub_now"),
        InlineKeyboardButton("🕒 Запланировать", callback_data="pub_queue_menu")
    )
    markup.add(
        InlineKeyboardButton("✏️ Редактировать", callback_data="edit_text"),
        InlineKeyboardButton("💰 Добавить рекламу", callback_data="add_ad")
    )
    return markup

def update_draft_inline(chat_id, target_id, draft):
    """Обновляет сообщение с черновиком (добавление рекламы и т.д.)"""
    markup = get_draft_markup(target_id)
    try:
        # Пробуем обновить как текст (для альбомов и длинных постов)
        bot.edit_message_text(text=draft['text'], chat_id=chat_id, message_id=target_id, parse_mode='HTML', reply_markup=markup)
    except:
        try:
            # Если это одиночное фото с подписью
            bot.edit_message_caption(caption=draft['text'], chat_id=chat_id, message_id=target_id, parse_mode='HTML', reply_markup=markup)
        except Exception as e:
            print(f"Ошибка обновления инлайна: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(message.chat.id, "Привет! Бот готов к работе.", reply_markup=get_main_menu())

@bot.message_handler(content_types=['text', 'photo'])
def handle_text_photo(message):
    if message.content_type == 'text':
        # Перехватываем кнопки меню, чтобы они не уходили в ИИ
        if message.text == "📝 Создать пост":
            bot.send_message(message.chat.id, "Отправь мне фото, текст или ссылку с описанием мода, и я сгенерирую пост! 🚀\n\n<i>Ты можешь отправить одно фото или целый альбом.</i>", parse_mode="HTML")
            return
        elif message.text == "📊 Статус очереди": 
            show_queue_page(message.chat.id, 0)
            return
        elif message.text == "💰 Реклама":
            msg = bot.send_message(message.chat.id, f"Текущая реклама:\n{get_ad_text() or 'ПУСТО'}\n\nПришли новый текст рекламы:", parse_mode='HTML', reply_markup=get_cancel_markup())
            bot.register_next_step_handler(msg, process_ad_step)
            return
        elif message.text == "➕ Добавить канал":
            msg = bot.send_message(message.chat.id, "Отправь @username нового канала (например: @my_new_channel):", reply_markup=get_cancel_markup())
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
            markup.add(InlineKeyboardButton(f"{'✅ ' if active_p == 'uz' else ''}🇺🇿 Узбекский (Стандарт)", callback_data="set_persona_uz"))
            markup.add(InlineKeyboardButton(f"{'✅ ' if active_p == 'ru' else ''}🇷🇺 Русский (Веселый)", callback_data="set_persona_ru"))
            markup.add(InlineKeyboardButton(f"{'✅ ' if active_p == 'en' else ''}🇬🇧 Английский (Захватывающий)", callback_data="set_persona_en"))
            bot.send_message(message.chat.id, "Выбери личность бота для генерации текста:", reply_markup=markup)
            return

    # Если это не кнопка меню, значит это КОНТЕНТ для поста
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
        if not user_input and message.photo:
            user_input = "Сделай красивый пост для этого мода."
        elif not user_input:
            return
        
        persona = get_active_persona(message.from_user.id)
        generated_text = ai_generator.generate_post(user_input, persona)
        photo_id = None
        
        if message.photo:
            bot.send_message(message.chat.id, "🎨 Обрабатываю фото и накладываю водяной знак...")
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            with open(temp_in, 'wb') as f: f.write(downloaded_file)
                
            # Безопасный вызов watermarker
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
    
    bot.send_message(chat_id, "🎨 Обрабатываю весь альбом и накладываю водяные знаки...")
    
    persona = get_active_persona(user_id)
    generated_text = ai_generator.generate_post(caption or "Опиши этот мод детально", persona)
    
    temp_files = []
    opened_files = [] 
    
    try:
        for i, m in enumerate(messages):
            file_info = bot.get_file(m.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            tin, tout = f"in_{media_group_id}_{i}.jpg", f"out_{media_group_id}_{i}.jpg"
            with open(tin, 'wb') as f: f.write(downloaded_file)
            
            # Накладываем знак
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

# --- ОБРАБОТЧИКИ "ОТМЕНЫ" И ШАГОВ ---
def process_ad_step(message):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(message.chat.id, "❌ Действие отменено.", reply_markup=get_main_menu())
        return
    save_ad_text(message.text)
    bot.send_message(message.chat.id, "✅ Реклама сохранена!", reply_markup=get_main_menu())

def process_add_channel_step(message):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(message.chat.id, "❌ Добавление канала отменено.", reply_markup=get_main_menu())
        return
    
    new_channel = message.text.strip()
    
    # Делаем проверку на формат юзернейма (@channel) или ID (-100...)
    if not new_channel.startswith('@') and not new_channel.replace('-', '').isdigit():
        new_channel = '@' + new_channel
        
    channels = get_channels()
    if new_channel in channels:
        bot.send_message(message.chat.id, f"⚠️ Канал {new_channel} уже есть в списке!", reply_markup=get_main_menu())
    else:
        with open("channels.txt", "a", encoding="utf-8") as f:
            f.write(new_channel + "\n")
        bot.send_message(message.chat.id, f"✅ Канал {new_channel} успешно добавлен!", reply_markup=get_main_menu())

def save_edited_text(message, target_id, chat_id):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(chat_id, "❌ Редактирование отменено.", reply_markup=get_main_menu())
        return
        
    draft = user_drafts.pop(target_id, None)
    if not draft: return
    
    draft['text'] = message.text
    
    try: bot.delete_message(chat_id, target_id)
    except: pass
    try: bot.delete_message(chat_id, message.message_id)
    except: pass
    
    bot.send_message(chat_id, "✅ Текст успешно обновлен!", reply_markup=get_main_menu())
    send_draft_preview(chat_id, draft)

def process_exact_time(message, draft_id, chat_id):
    if message.text and message.text.lower() in ['отмена', '❌ отмена']:
        bot.send_message(chat_id, "❌ Планирование отменено.", reply_markup=get_main_menu())
        return

    try:
        # 1. Считываем время, которое ввел пользователь
        dt_naive = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        
        # 2. ЖЕСТКО привязываем это время к часовому поясу Ташкента
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        dt_aware = tashkent_tz.localize(dt_naive)
        
        # 3. Получаем правильный универсальный timestamp
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
        msg = bot.send_message(chat_id, "❌ Неверный формат! Введи заново (ДД.ММ.ГГГГ ЧЧ:ММ):", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_exact_time, draft_id, chat_id)

# --- ОБРАБОТКА CALLBACK ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith('q_'):
        parts = call.data.split('_')
        action, val = parts[1], int(parts[2])

        if action == 'page': show_queue_page(call.message.chat.id, val, call.message.message_id)
        elif action == 'del':
            database.delete_from_queue(val)
            bot.answer_callback_query(call.id, "🗑 Пост удален!")
            show_queue_page(call.message.chat.id, 0, call.message.message_id)
        elif action == 'pub':
            posts = database.get_all_pending()
            post = next((p for p in posts if p[0] == val), None)
            if post and publish_post_data(post[0], post[1], post[2], post[3], post[4] or config.DEFAULT_CHANNEL):
                bot.answer_callback_query(call.id, "🚀 Опубликовано!")
                show_queue_page(call.message.chat.id, 0, call.message.message_id)
            else: bot.answer_callback_query(call.id, "❌ Ошибка публикации!", show_alert=True)
            return

    if call.data.startswith("set_channel_"):
        channel = call.data.replace("set_channel_", "")
        active_channels[call.from_user.id] = channel
        bot.answer_callback_query(call.id, f"Актуальный канал: {channel}")
        bot.edit_message_text(f"✅ Выбран канал: <b>{channel}</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")
        return

    if call.data.startswith("set_persona_"):
        persona = call.data.replace("set_persona_", "")
        user_personas[call.from_user.id] = persona
        lang_names = {"uz": "Узбекский", "ru": "Русский", "en": "Английский"}
        bot.answer_callback_query(call.id, f"Стиль изменен на: {lang_names.get(persona)}")
        bot.edit_message_text(f"✅ Установлен стиль постов: <b>{lang_names.get(persona)}</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")
        return

    target_id = call.message.message_id
    draft = user_drafts.get(target_id)
    
    if not draft and not call.data.startswith("sched_"):
        return bot.answer_callback_query(call.id, "Черновик устарел.", show_alert=True)

    if call.data == "edit_text":
        raw_text = html.escape(draft['text'])
        msg = bot.send_message(call.message.chat.id, f"✏️ <b>Нажми на код ниже, чтобы скопировать его:</b>\n\n<code>{raw_text}</code>\n\nВставь, исправь и отправь мне!", parse_mode="HTML", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, save_edited_text, target_id, call.message.chat.id)
        return

    if call.data == "add_ad":
        if draft['ad_added']: return bot.answer_callback_query(call.id, "Уже есть!", show_alert=True)
        ad_text = get_ad_text()
        if not ad_text: return bot.answer_callback_query(call.id, "Задай рекламу в меню!", show_alert=True)
        
        draft['text'] += f"\n\n<blockquote>{ad_text}</blockquote>"
        draft['ad_added'] = True
        # Используем новую функцию вместо ошибки
        update_draft_inline(call.message.chat.id, target_id, draft) 
        bot.answer_callback_query(call.id, "Реклама добавлена!")
        return

    if call.data == "pub_now":
        if publish_post_data(-1, draft['photo'], draft['text'], draft['document'], draft['channel']):
            bot.answer_callback_query(call.id, "✅ Опубликовано!")
            bot.edit_message_reply_markup(call.message.chat.id, target_id, reply_markup=None)
            bot.send_message(call.message.chat.id, f"🚀 Отправлено в {draft['channel']}!")
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
        bot.edit_message_reply_markup(call.message.chat.id, target_id, reply_markup=markup)
        return

    if call.data == "back_to_draft":
        bot.edit_message_reply_markup(call.message.chat.id, target_id, reply_markup=get_draft_markup(target_id))
        return

    if call.data.startswith("sched_interval_"):
        parts = call.data.split('_')
        hours, draft_id = int(parts[2]), int(parts[3])
        target_draft = user_drafts.get(draft_id)
        
        if not target_draft: return bot.answer_callback_query(call.id, "Ошибка.")
        timestamp = int((datetime.now() + timedelta(hours=hours)).timestamp())
        
        database.add_to_queue(target_draft['photo'], target_draft['text'], target_draft['document'], target_draft['channel'], timestamp)
        bot.edit_message_reply_markup(call.message.chat.id, draft_id, reply_markup=None)
        bot.send_message(call.message.chat.id, f"🕒 Запланировано (через {hours} ч.) для {target_draft['channel']}")
        del user_drafts[draft_id]
        return

    if call.data.startswith("sched_exact_"):
        draft_id = int(call.data.split('_')[2])
        msg = bot.send_message(call.message.chat.id, "📅 Отправь дату в формате `ДД.ММ.ГГГГ ЧЧ:ММ`\nНапример: `25.10.2026 15:30`", parse_mode="Markdown", reply_markup=get_cancel_markup())
        bot.register_next_step_handler(msg, process_exact_time, draft_id, call.message.chat.id)
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

print("Бот v11.3 (Исправленный Watermark + FSM) запущен!")
while True:
    try:
        bot.polling(none_stop=True, timeout=90)
    except Exception as e:
        time.sleep(5)