import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
import time
import threading
import os
import html
import config
import database
import ai_generator
import watermarker
import comments_analyzer
import utils
import markups
import core
import pytz
from datetime import datetime, timedelta
from bot_instance import bot

database.init_db()
album_cache = {}
user_states = {}

# --- SCHEDULER ---
jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')}
scheduler = BackgroundScheduler(jobstores=jobstores)
if not scheduler.get_job('queue_process'):
    scheduler.add_job(core.process_queue, 'interval', minutes=1, id='queue_process', replace_existing=True)
scheduler.start()

def show_queue_page(chat_id, page, message_id=None):
    posts = database.get_all_pending()
    if not posts:
        text = "━━━━━━━━━━━━━\n📭 <b>Очередь пуста</b>\n━━━━━━━━━━━━━"
        if message_id: bot.edit_message_text(text, chat_id, message_id, parse_mode='HTML')
        else: bot.send_message(chat_id, text, parse_mode='HTML')
        return
    if page >= len(posts): page = len(posts) - 1
    if page < 0: page = 0
    post = posts[page]
    msg_text = utils.format_queue_post(post, page + 1, len(posts))
    markup = markups.get_queue_manage_markup(post[0], page)
    if message_id:
        try: bot.edit_message_text(msg_text, chat_id, message_id, parse_mode='HTML', reply_markup=markup)
        except: pass
    else: bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type != 'private': return
    user_states[message.chat.id] = None
    greeting = utils.get_time_greeting()
    bot.send_message(message.chat.id, f"🌟 <b>{greeting}!</b>\n\nЯ твой профессиональный менеджер Minecraft-канала. Отправь мне данные для нового поста!", reply_markup=markups.get_main_menu(), parse_mode='HTML')

@bot.message_handler(content_types=['text', 'photo'])
def handle_text_photo(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if message.chat.type in ['group', 'supergroup']:
        if message.text and not message.text.startswith('/'):
            database.save_comment(message.from_user.first_name, message.text, int(time.time()))
        return

    state_data = user_states.get(chat_id)
    if state_data and state_data.get('state') == 'ai_chat':
        if message.text == "❌ Отмена":
            user_states[chat_id] = None
            bot.send_message(chat_id, "🔌 <b>Связь с ИИ разорвана.</b>", reply_markup=markups.get_main_menu(), parse_mode='HTML')
            return
        bot.send_chat_action(chat_id, 'typing')
        response = ai_generator.chat_with_ai(message.text)
        bot.send_message(chat_id, f"🤖 <b>ИИ:</b>\n\n{response}", parse_mode='HTML', reply_markup=markups.get_cancel_markup())
        return

    if message.content_type == 'text':
        text = message.text
        if text == "➕ Создать пост":
            bot.send_message(chat_id, "📬 <b>Отправь мне ссылку или описание мода.</b>", parse_mode='HTML')
        elif text == "🤖 Чат с ИИ":
            user_states[chat_id] = {'state': 'ai_chat'}
            bot.send_message(chat_id, "🧠 <b>Режим прямого общения с ИИ активирован.</b>", reply_markup=markups.get_cancel_markup(), parse_mode='HTML')
        elif text == "🌍 Язык":
            lang, _ = database.get_user_settings(user_id)
            bot.send_message(chat_id, f"🌐 <b>Текущий язык: {lang.upper()}</b>", reply_markup=markups.get_language_menu(), parse_mode='HTML')
        elif text == "📋 Очередь":
            show_queue_page(chat_id, 0)
        elif text == "📊 Статистика":
            core.show_stats(chat_id, len(utils.get_channels()))
        elif text == "⚙️ Настройки":
            bot.send_message(chat_id, "🛠 <b>Настройки:</b>", reply_markup=markups.get_settings_menu(), parse_mode='HTML')
        elif text == "🧐 Анализ":
            msg = bot.send_message(chat_id, "🔍 <b>Анализирую...</b>", parse_mode='HTML')
            report = comments_analyzer.analyze_comments()
            bot.delete_message(chat_id, msg.message_id)
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🗑 Очистить", callback_data="clear_comments_db"))
            bot.send_message(chat_id, report, parse_mode="HTML", reply_markup=markup)
        elif text == "❌ Отмена":
            user_states[chat_id] = None
            bot.send_message(chat_id, "🏠 <b>Главное меню</b>", reply_markup=markups.get_main_menu(), parse_mode='HTML')
        else:
            if not message.media_group_id:
                start_generation(chat_id, user_id, text, None)
            elif message.media_group_id not in album_cache:
                album_cache[message.media_group_id] = []
                threading.Timer(2.0, process_album_immediate, args=[message.media_group_id, chat_id, user_id]).start()
            if message.media_group_id: album_cache[message.media_group_id].append(message)
    
    elif message.photo:
        if not message.media_group_id:
            start_generation(chat_id, user_id, message.caption, message.photo[-1].file_id)
        elif message.media_group_id not in album_cache:
            album_cache[message.media_group_id] = []
            threading.Timer(2.0, process_album_immediate, args=[message.media_group_id, chat_id, user_id]).start()
        if message.media_group_id: album_cache[message.media_group_id].append(message)

def process_album_immediate(media_group_id, chat_id, user_id):
    messages = album_cache.pop(media_group_id, None)
    if not messages: return
    caption = next((m.caption for m in messages if m.caption), "")
    photo_ids = ",".join([m.photo[-1].file_id for m in messages])
    start_generation(chat_id, user_id, caption, photo_ids, is_album=True)

def start_generation(chat_id, user_id, user_input, photo_id, is_album=False):
    msg = bot.send_message(chat_id, "🤖 <b>Нейросеть пишет пост...</b>", parse_mode='HTML')
    lang, _ = database.get_user_settings(user_id)
    
    generated_text = ai_generator.generate_post(user_input or "Minecraft контент", persona=lang)
    bot.delete_message(chat_id, msg.message_id)
    
    final_photo_id = photo_id
    if photo_id and not is_album:
        bot.send_chat_action(chat_id, 'upload_photo')
        temp_in, temp_out = f"in_{chat_id}.jpg", f"out_{chat_id}.jpg"
        file_info = bot.get_file(photo_id)
        with open(temp_in, 'wb') as f: f.write(bot.download_file(file_info.file_path))
        watermarker.add_watermark(temp_in, temp_out)
        with open(temp_out if os.path.exists(temp_out) else temp_in, 'rb') as f:
            sent = bot.send_photo(chat_id, f)
            final_photo_id = sent.photo[-1].file_id
            bot.delete_message(chat_id, sent.message_id)
        if os.path.exists(temp_in): os.remove(temp_in)
        if os.path.exists(temp_out): os.remove(temp_out)

    draft = {'photo': final_photo_id, 'text': generated_text, 'document': None, 'ad_added': False, 'channel': utils.get_active_channel(user_id)}
    database.save_draft(user_id, final_photo_id, generated_text, None, draft['channel'])
    send_draft_preview(chat_id, draft)

def send_draft_preview(chat_id, draft):
    if draft['photo'] and ',' in draft['photo']:
        bot.send_media_group(chat_id, [telebot.types.InputMediaPhoto(m) for m in draft['photo'].split(',')])
        sent = bot.send_message(chat_id, draft['text'], parse_mode='HTML')
    elif draft['photo']:
        if len(draft['text']) <= 1024: sent = bot.send_photo(chat_id, draft['photo'], caption=draft['text'], parse_mode='HTML')
        else:
            bot.send_photo(chat_id, draft['photo'])
            sent = bot.send_message(chat_id, draft['text'], parse_mode='HTML')
    else: sent = bot.send_message(chat_id, draft['text'], parse_mode='HTML')
    bot.edit_message_reply_markup(chat_id, sent.message_id, reply_markup=markups.get_draft_markup(sent.message_id))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id, user_id = call.message.chat.id, call.from_user.id
    
    if call.data.startswith('set_lang_'):
        database.set_user_setting(user_id, lang=call.data.replace('set_lang_', ''))
        bot.answer_callback_query(call.id, "✅ Язык изменен")
        bot.delete_message(chat_id, call.message.message_id)
    
    elif call.data == "csv_export":
        filename, _ = utils.generate_csv_export()
        if filename:
            with open(filename, 'rb') as f: bot.send_document(chat_id, f)
            os.remove(filename)
    
    elif call.data == "db_backup":
        if os.path.exists('bot_data.db'):
            with open('bot_data.db', 'rb') as f: bot.send_document(chat_id, f)

    elif call.data == "set_ad_text":
        msg = bot.send_message(chat_id, "📝 Введи текст рекламы:", reply_markup=markups.get_cancel_markup())
        bot.register_next_step_handler(msg, process_ad_step)

    elif call.data == "add_new_channel":
        msg = bot.send_message(chat_id, "📢 Введи @username канала:", reply_markup=markups.get_cancel_markup())
        bot.register_next_step_handler(msg, process_add_channel_step)

    elif call.data.startswith('set_channel_'):
        database.set_user_setting(user_id, channel=call.data.replace('set_channel_', ''))
        bot.delete_message(chat_id, call.message.message_id)

    elif call.data.startswith('q_'):
        parts = call.data.split('_')
        action, val = parts[1], int(parts[2])
        if action == 'page': show_queue_page(chat_id, val, call.message.message_id)
        elif action == 'del': database.delete_from_queue(val); show_queue_page(chat_id, 0, call.message.message_id)
        elif action == 'edit':
            msg = bot.send_message(chat_id, "📝 Введи новый текст:", reply_markup=markups.get_cancel_markup())
            bot.register_next_step_handler(msg, save_edited_text, None, chat_id, True, val)
        elif action == 'pub':
            post = next((p for p in database.get_all_pending() if p[0] == val), None)
            if post and core.publish_post_data(post[0], post[1], post[2], post[3], post[4] or config.DEFAULT_CHANNEL):
                show_queue_page(chat_id, 0, call.message.message_id)
        elif action == 'time':
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_publish_queue_menu(val, "qtime_"))

    elif call.data == "rewrite_menu": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_rewrite_menu())
    elif call.data.startswith("rw_"):
        draft = database.get_draft(user_id)
        if draft:
            draft['text'] = ai_generator.rewrite_post(draft['text'], call.data.split("_")[1])
            database.save_draft(user_id, draft['photo'], draft['text'], draft['document'], draft['channel'])
            finalize_draft_update(chat_id, call.message.message_id, draft)

    elif call.data == "pub_now":
        draft = database.get_draft(user_id)
        if draft and core.publish_post_data(-1, draft['photo'], draft['text'], draft['document'], draft['channel']):
            database.record_published_post(draft['photo'], draft['text'], draft['document'], draft['channel'])
            database.clear_draft(user_id)
            bot.delete_message(chat_id, call.message.message_id)

    elif call.data == "pub_queue_menu": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_publish_queue_menu(call.message.message_id))
    elif call.data == "back_to_draft": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_draft_markup(call.message.message_id))
    elif call.data == "cancel_action": bot.delete_message(chat_id, call.message.message_id)

def finalize_draft_update(chat_id, message_id, draft):
    try: bot.edit_message_text(draft['text'], chat_id, message_id, parse_mode='HTML', reply_markup=markups.get_draft_markup(message_id))
    except:
        try: bot.edit_message_caption(draft['text'], chat_id, message_id, parse_mode='HTML', reply_markup=markups.get_draft_markup(message_id))
        except: pass

def process_ad_step(message):
    if message.text == "❌ Отмена": return
    utils.save_ad_text(message.text)
    bot.send_message(message.chat.id, "✅ Реклама сохранена!", reply_markup=markups.get_main_menu())

def process_add_channel_step(message):
    if message.text == "❌ Отмена": return
    new_ch = message.text.strip()
    if not new_ch.startswith('@'): new_ch = '@' + new_ch
    with open("channels.txt", "a", encoding="utf-8") as f: f.write(new_ch + "\n")
    bot.send_message(message.chat.id, f"✅ Канал {new_ch} добавлен!", reply_markup=markups.get_main_menu())

def save_edited_text(message, target_id, chat_id, is_queue=False, post_id=None):
    if message.text == "❌ Отмена": return
    if is_queue:
        database.update_post_text(post_id, message.text)
        show_queue_page(chat_id, 0)
    else:
        draft = database.get_draft(message.from_user.id)
        if draft:
            draft['text'] = message.text
            database.save_draft(message.from_user.id, draft['photo'], draft['text'], draft['document'], draft['channel'])
            send_draft_preview(chat_id, draft)

bot.polling(none_stop=True)
