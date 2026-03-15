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
import web_searcher
import pytz
import re
from datetime import datetime, timedelta
from bot_instance import bot
from strings import MESSAGES, BUTTONS

# --- WEB APP (TMA) ---
try:
    from webapp.api import run_api
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    print("🚀 Web App API thread started.")
except Exception as e:
    print(f"⚠️ Could not start Web App API: {e}")

database.init_db()
album_cache = {}
user_states = {}

# --- SCHEDULER ---
jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')}
scheduler = BackgroundScheduler(jobstores=jobstores)
if not scheduler.get_job('queue_process'):
    scheduler.add_job(core.process_queue, 'interval', minutes=1, id='queue_process', replace_existing=True)
scheduler.start()

def get_user_lang(user_id):
    lang, _ = database.get_user_settings(user_id)
    return lang or 'uz'

def show_queue_page(chat_id, page, message_id=None):
    user_id = chat_id # В личке совпадает
    lang = get_user_lang(user_id)
    posts = database.get_all_pending()
    if not posts:
        text = MESSAGES[lang]['queue_empty']
        if message_id: bot.edit_message_text(text, chat_id, message_id, parse_mode='HTML')
        else: bot.send_message(chat_id, text, parse_mode='HTML')
        return
    if page >= len(posts): page = len(posts) - 1
    if page < 0: page = 0
    post = posts[page]
    msg_text = utils.format_queue_post(post, page + 1, len(posts))
    markup = markups.get_queue_manage_markup(post[0], page, lang)
    if message_id:
        try: bot.edit_message_text(msg_text, chat_id, message_id, parse_mode='HTML', reply_markup=markup)
        except: pass
    else: bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.chat.type != 'private': return
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    user_states[message.chat.id] = None
    text = MESSAGES[lang]['welcome']
    bot.send_message(message.chat.id, text, reply_markup=markups.get_main_menu(lang), parse_mode='HTML')

# Кэш для объединения пересланных постов от админа
admin_media_cache = {}

@bot.message_handler(content_types=['text', 'photo', 'document', 'video', 'audio', 'voice'])
def handle_text_photo_file(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    text = message.text if message.content_type == 'text' else message.caption

    # DEBUG LOG
    if text: print(f"📩 [{chat_id}] Message: {text}")

    # --- АВТОМАТИЗАЦИЯ ДЛЯ ЮЗЕРБОТА (АДМИНА) ---
    state_data = user_states.get(chat_id)
    is_creating = state_data and state_data.get('state') == 'creating_post'

    if user_id in getattr(config, 'ADMIN_IDS', []) and message.chat.type == 'private' and not is_creating:
        
        # ПРОВЕРКА: ВКЛЮЧЕН ЛИ АВТОПОСТИНГ
        if database.is_auto_post_on():
            # 1. Кэширование фото/текста
            if message.photo or (message.content_type == 'text' and not message.document):
                admin_media_cache[user_id] = {
                    'text': text,
                    'photo_id': message.photo[-1].file_id if message.photo else None,
                    'time': time.time()
                }
                print("🖼️/📝 Данные админа сохранены в кэш")

            # 2. Обработка файла (мода)
            if (message.document or message.video) and message.chat.type == 'private':
                doc_id = message.document.file_id if message.document else message.video.file_id
                file_unique_id = message.document.file_unique_id if message.document else message.video.file_unique_id
                
                # ПРОВЕРКА НА ДУБЛИКАТ
                if database.is_duplicate(file_unique_id):
                    bot.send_message(chat_id, "⏩ Мод уже есть в базе, пропускаю.")
                    return

                bot.send_message(chat_id, "🤖 Мод получен. Обработка и водяной знак...")
                
                cache = admin_media_cache.get(user_id, {})
                cache_text = cache.get('text', "")
                cache_photo = cache.get('photo_id')
                cache_time = cache.get('time', 0)
                
                # Если в кэше пусто, попробуем взять текст из самого сообщения с файлом
                final_text = text or cache_text
                if not final_text:
                    # Если текста совсем нет, попробуем использовать имя файла
                    file_name = message.document.file_name if message.document else "Minecraft Mod"
                    final_text = f"Mod: {file_name}"
                    
                raw_photo = (message.photo[-1].file_id if message.photo else None) or cache_photo
                
                # Кэш фото/текста действителен 10 минут
                if time.time() - cache_time > 600:
                    raw_photo = cache_photo if cache_photo else None
                    if not text and cache_text: final_text = cache_text

                try:
                    # Генерируем текст через ИИ
                    ai_text = ai_generator.generate_post(final_text, lang)
                    
                    # Если ИИ отклонил пост или вернул ошибку
                    if not ai_text or "REJECT" in ai_text.upper() or "ERROR" in ai_text.upper():
                        bot.send_message(chat_id, f"⏩ Пост отклонен или ошибка ИИ: {ai_text}")
                        return

                    # НАЛОЖЕНИЕ ВОДЯНОГО ЗНАКА
                    final_photo_id = None
                    if raw_photo:
                        try:
                            temp_in, temp_out = f"auto_in_{chat_id}.jpg", f"auto_out_{chat_id}.jpg"
                            file_info = bot.get_file(raw_photo)
                            downloaded_file = bot.download_file(file_info.file_path)
                            with open(temp_in, 'wb') as f: f.write(downloaded_file)
                            
                            watermarker.add_watermark(temp_in, temp_out)
                            
                            with open(temp_out if os.path.exists(temp_out) else temp_in, 'rb') as f:
                                sent_photo = bot.send_photo(chat_id, f, caption="🎨 Накладываю водяной знак...")
                                final_photo_id = sent_photo.photo[-1].file_id
                                bot.delete_message(chat_id, sent_photo.message_id)
                                
                            if os.path.exists(temp_in): os.remove(temp_in)
                            if os.path.exists(temp_out): os.remove(temp_out)
                        except Exception as we:
                            print(f"⚠️ Ошибка водяного знака: {we}")
                            final_photo_id = raw_photo

                    # Добавляем в очередь
                    new_time = core.get_next_schedule_time()
                    database.add_to_queue(final_photo_id, ai_text, doc_id, config.DEFAULT_CHANNEL, new_time, file_unique_id)
                    bot.send_message(chat_id, f"✅ Готово! Пост с водяным знаком в очереди на {datetime.fromtimestamp(new_time).strftime('%d.%m %H:%M')}")
                    
                    if user_id in admin_media_cache: del admin_media_cache[user_id]
                    return
                except Exception as e:
                    bot.send_message(chat_id, f"❌ Ошибка авто-постинга: {e}")

    if message.chat.type in ['group', 'supergroup']:
        if text and not text.startswith('/'):
            database.save_comment(message.from_user.first_name, text, int(time.time()))
            print(f"💬 Сохранен комментарий от {message.from_user.first_name}: {text[:50]}...")
        return

    # СРАЗУ ПРОВЕРЯЕМ ОТМЕНУ (ВЫСШИЙ ПРИОРИТЕТ)
    if text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]:
        user_states[chat_id] = None
        bot.send_message(chat_id, MESSAGES[lang]['ai_chat_off'], reply_markup=markups.get_main_menu(lang), parse_mode='HTML')
        return

    # --- ОБРАБОТКА REPLY ---
    if message.reply_to_message:
        file_id = None
        if message.document: file_id = message.document.file_id
        elif message.video: file_id = message.video.file_id
        elif message.audio: file_id = message.audio.file_id
        elif message.photo: file_id = message.photo[-1].file_id
        
        if file_id:
            bot.send_chat_action(chat_id, 'upload_document')
            draft = database.get_draft(user_id)
            if draft:
                if message.photo: draft['photo'] = file_id
                else: draft['document'] = file_id
                database.save_draft(user_id, draft['photo'], draft['text'], draft['document'], draft['channel'], 1 if draft.get('ad_added') else 0)
                bot.reply_to(message, MESSAGES[lang]['file_attached'])
                send_draft_preview(chat_id, draft)
                return

    state_data = user_states.get(chat_id)
    if state_data:
        if state_data.get('state') == 'ai_chat':
            bot.send_chat_action(chat_id, 'typing')
            stats = database.get_stats()
            channel = utils.get_active_channel(user_id)
            comments = database.get_all_comments()[-30:] # Берем больше
            comm_text = "\n".join([f"- {c[0]}: {c[1]}" for c in comments])
            context_msg = f"[Context: Bot for @lazikosmods. Queue: {stats['queue']} posts. Channel: {channel}. Comments:\n{comm_text or 'No'}] {message.text}"
            response = ai_generator.chat_with_ai(context_msg, lang)
            bot.send_message(chat_id, f"🤖 <b>AI:</b>\n\n{response}", parse_mode='HTML', reply_markup=markups.get_cancel_markup(lang))
            return
        elif state_data.get('state') == 'creating_post':
            user_states[chat_id] = None # Сбрасываем
            bot.send_chat_action(chat_id, 'typing')
            if not message.media_group_id:
                start_generation(chat_id, user_id, text, (message.photo[-1].file_id if message.photo else None))
            elif message.media_group_id not in album_cache:
                album_cache[message.media_group_id] = []
                threading.Timer(2.0, process_album_immediate, args=[message.media_group_id, chat_id, user_id]).start()
            if message.media_group_id: album_cache[message.media_group_id].append(message)
            return

    if message.content_type == 'text':
        text = message.text
        if text in [BUTTONS['uz']['create'], BUTTONS['ru']['create'], BUTTONS['en']['create']]:
            user_states[chat_id] = {'state': 'creating_post'}
            bot.send_message(chat_id, "📬 <b>Link / Info?</b>", parse_mode='HTML')
            return
        elif text in [BUTTONS['uz']['ai_chat'], BUTTONS['ru']['ai_chat'], BUTTONS['en']['ai_chat']]:
            user_states[chat_id] = {'state': 'ai_chat'}
            bot.send_message(chat_id, MESSAGES[lang]['ai_chat_active'], reply_markup=markups.get_cancel_markup(lang), parse_mode='HTML')
        elif text in [BUTTONS['uz']['lang'], BUTTONS['ru']['lang'], BUTTONS['en']['lang']]:
            bot.send_message(chat_id, MESSAGES[lang]['choose_lang'], reply_markup=markups.get_language_menu(), parse_mode='HTML')
        elif text in [BUTTONS['uz']['channels'], BUTTONS['ru']['channels'], BUTTONS['en']['channels']]:
            channels = utils.get_channels()
            active = utils.get_active_channel(user_id)
            bot.send_message(chat_id, f"📢 <b>{BUTTONS[lang]['channels']}:</b>", reply_markup=markups.get_channels_markup(channels, active), parse_mode='HTML')
        elif text in [BUTTONS['uz']['queue'], BUTTONS['ru']['queue'], BUTTONS['en']['queue']]:
            bot.send_chat_action(chat_id, 'typing')
            show_queue_page(chat_id, 0)
        elif text in [BUTTONS['uz']['stats'], BUTTONS['ru']['stats'], BUTTONS['en']['stats']]:
            core.show_stats(chat_id, len(utils.get_channels()), lang)
        elif text in [BUTTONS['uz']['settings'], BUTTONS['ru']['settings'], BUTTONS['en']['settings']]:
            auto_p = database.is_auto_post_on()
            bot.send_message(chat_id, MESSAGES[lang]['settings'], reply_markup=markups.get_settings_menu(lang, auto_p), parse_mode='HTML')
        elif text in [BUTTONS['uz']['analyze'], BUTTONS['ru']['analyze'], BUTTONS['en']['analyze']]:
            bot.send_chat_action(chat_id, 'typing')
            msg = bot.send_message(chat_id, MESSAGES[lang]['analyzing'], parse_mode='HTML')
            report = comments_analyzer.analyze_comments()
            bot.delete_message(chat_id, msg.message_id)
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🗑 Clear", callback_data="clear_comments_db"))
            bot.send_message(chat_id, report, parse_mode="HTML", reply_markup=markup)
        elif text in [BUTTONS['uz']['trends'], BUTTONS['ru']['trends'], BUTTONS['en']['trends']]:
            bot.send_chat_action(chat_id, 'typing')
            msg = bot.send_message(chat_id, MESSAGES[lang]['searching_trends'], parse_mode='HTML')
            
            trends = web_searcher.get_all_trends()
            bot.delete_message(chat_id, msg.message_id)
            
            if not trends:
                bot.send_message(chat_id, "⚠️ No trends found.")
                return
            
            res_text = MESSAGES[lang]['trending_title']
            for i, item in enumerate(trends, 1):
                icon = "🎬" if item['source'] == "YouTube" else "📦"
                res_text += f"{i}. {icon} <a href='{item['url']}'>{item['title']}</a>\n"
            
            bot.send_message(chat_id, res_text, parse_mode='HTML', disable_web_page_preview=True)
        else:
            bot.send_chat_action(chat_id, 'typing')
            if not message.media_group_id:
                start_generation(chat_id, user_id, text, None)
            elif message.media_group_id not in album_cache:
                album_cache[message.media_group_id] = []
                threading.Timer(2.0, process_album_immediate, args=[message.media_group_id, chat_id, user_id]).start()
            if message.media_group_id: album_cache[message.media_group_id].append(message)
    
    elif message.photo:
        bot.send_chat_action(chat_id, 'upload_photo')
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
    lang = get_user_lang(user_id)
    msg = bot.send_message(chat_id, MESSAGES[lang]['generation_start'], parse_mode='HTML')
    generated_text = ai_generator.generate_post(user_input or "Minecraft", persona=lang)
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
    lang = get_user_lang(chat_id)
    bot.send_chat_action(chat_id, 'typing')
    doc_info = f"\n\n📄 <b>File:</b> Yes" if draft.get('document') else ""
    full_text = draft['text'] + doc_info
    if draft['photo'] and ',' in draft['photo']:
        bot.send_media_group(chat_id, [telebot.types.InputMediaPhoto(m) for m in draft['photo'].split(',')])
        sent = bot.send_message(chat_id, full_text, parse_mode='HTML')
    elif draft['photo']:
        if len(full_text) <= 1024: sent = bot.send_photo(chat_id, draft['photo'], caption=full_text, parse_mode='HTML')
        else:
            bot.send_photo(chat_id, draft['photo'])
            sent = bot.send_message(chat_id, full_text, parse_mode='HTML')
    else: sent = bot.send_message(chat_id, full_text, parse_mode='HTML')
    bot.edit_message_reply_markup(chat_id, sent.message_id, reply_markup=markups.get_draft_markup(lang))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id, user_id = call.message.chat.id, call.from_user.id
    lang = get_user_lang(user_id)
    
    if call.data.startswith('set_lang_'):
        new_lang = call.data.replace('set_lang_', '')
        database.set_user_setting(user_id, lang=new_lang)
        bot.answer_callback_query(call.id, "✅ Done")
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, MESSAGES[new_lang]['welcome'], reply_markup=markups.get_main_menu(new_lang), parse_mode='HTML')
    
    elif call.data == "csv_export":
        filename, _ = utils.generate_csv_export()
        if filename:
            with open(filename, 'rb') as f: bot.send_document(chat_id, f)
            os.remove(filename)
    
    elif call.data == "db_backup":
        if os.path.exists(database.DB_PATH):
            with open(database.DB_PATH, 'rb') as f: bot.send_document(chat_id, f)

    elif call.data == "set_ad_text":
        msg = bot.send_message(chat_id, MESSAGES[lang]['enter_ad'], reply_markup=markups.get_cancel_markup(lang))
        bot.register_next_step_handler(msg, process_ad_step)

    elif call.data == "add_new_channel":
        msg = bot.send_message(chat_id, MESSAGES[lang]['enter_channel'], reply_markup=markups.get_cancel_markup(lang))
        bot.register_next_step_handler(msg, process_add_channel_step)

    elif call.data == "toggle_auto_post":
        current = database.is_auto_post_on()
        new_val = 0 if current else 1
        database.set_global_setting('auto_post_enabled', new_val)
        auto_p = (new_val == 1)
        try:
            bot.edit_message_reply_markup(chat_id, call.message.message_id, 
                                          reply_markup=markups.get_settings_menu(lang, auto_p))
            status_text = "🟢 ON" if auto_p else "🔴 OFF"
            bot.answer_callback_query(call.id, f"Auto-Post: {status_text}")
        except: pass

    elif call.data == "clear_comments_db":
        database.clear_comments()
        bot.answer_callback_query(call.id, "✅ Cleared")
        bot.delete_message(chat_id, call.message.message_id)

    elif "_int_" in call.data or "_ex_" in call.data:
        parts = call.data.split('_')
        prefix, action, val, target_id = parts[0], parts[1], int(parts[2]), int(parts[3])
        if action == "int":
            new_time = int(time.time()) + (val * 3600)
            if prefix == "sc":
                draft = database.get_draft(user_id)
                if draft:
                    database.add_to_queue(draft['photo'], draft['text'], draft['document'], draft['channel'], new_time)
                    database.clear_draft(user_id)
                    bot.delete_message(chat_id, call.message.message_id)
            else:
                database.update_post_time(target_id, new_time)
                show_queue_page(chat_id, 0, call.message.message_id)
            bot.answer_callback_query(call.id, f"✅ {datetime.fromtimestamp(new_time).strftime('%H:%M')}")
            if prefix == "sc": bot.send_message(chat_id, "🏠", reply_markup=markups.get_main_menu(lang))
        elif action == "ex":
            msg = bot.send_message(chat_id, "🕒 <b>Enter (HH:MM / DD.MM HH:MM):</b>", reply_markup=markups.get_cancel_markup(lang), parse_mode='HTML')
            bot.register_next_step_handler(msg, process_custom_time, prefix, target_id, call.message.message_id)

    elif call.data.startswith('set_channel_'):
        database.set_user_setting(user_id, channel=call.data.replace('set_channel_', ''))
        bot.delete_message(chat_id, call.message.message_id)
        bot.send_message(chat_id, f"✅ Active: {call.data.replace('set_channel_', '')}", reply_markup=markups.get_main_menu(lang))

    elif call.data.startswith('q_'):
        parts = call.data.split('_')
        action, val = parts[1], int(parts[2])
        if action == 'page': show_queue_page(chat_id, val, call.message.message_id)
        elif action == 'del': database.delete_from_queue(val); show_queue_page(chat_id, 0, call.message.message_id)
        elif action == 'edit':
            msg = bot.send_message(chat_id, MESSAGES[lang]['enter_new_text'], reply_markup=markups.get_cancel_markup(lang))
            bot.register_next_step_handler(msg, save_edited_text, None, chat_id, True, val)
        elif action == 'pub':
            post = next((p for p in database.get_all_pending() if p[0] == val), None)
            if post and core.publish_post_data(post[0], post[1], post[2], post[3], post[4] or config.DEFAULT_CHANNEL):
                show_queue_page(chat_id, 0, call.message.message_id)
        elif action == 'time':
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_publish_queue_menu(val, "qt", lang))

    elif call.data == "rewrite_menu": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_rewrite_menu(lang))
    elif call.data.startswith("rw_"):
        draft = database.get_draft(user_id)
        if draft:
            bot.send_chat_action(chat_id, 'typing')
            draft['text'] = ai_generator.rewrite_post(draft['text'], call.data.split("_")[1], lang)
            database.save_draft(user_id, draft['photo'], draft['text'], draft['document'], draft['channel'], 1 if draft.get('ad_added') else 0)
            finalize_draft_update(chat_id, call.message.message_id, draft)

    elif call.data == "edit_text":
        draft = database.get_draft(user_id)
        if draft:
            bot.send_message(chat_id, "📌 <b>Current text:</b>", parse_mode='HTML')
            bot.send_message(chat_id, draft['text'])
        msg = bot.send_message(chat_id, MESSAGES[lang]['enter_new_text'], reply_markup=markups.get_cancel_markup(lang))
        bot.register_next_step_handler(msg, save_edited_text, call.message.message_id, chat_id)

    elif call.data == "add_to_smart_q":
        draft = database.get_draft(user_id)
        if draft:
            last_time = database.get_last_scheduled_time()
            now = int(time.time())
            interval = config.SMART_QUEUE_INTERVAL_HOURS * 3600
            new_time = (last_time + interval) if (last_time and last_time > now) else (now + 3600)
            database.add_to_queue(draft['photo'], draft['text'], draft['document'], draft['channel'], new_time)
            database.clear_draft(user_id)
            bot.answer_callback_query(call.id, f"✅ {datetime.fromtimestamp(new_time).strftime('%d.%m %H:%M')}")
            bot.delete_message(chat_id, call.message.message_id)
            bot.send_message(chat_id, "🏠", reply_markup=markups.get_main_menu(lang))

    elif call.data == "add_ad":
        ad_text = utils.get_ad_text()
        draft = database.get_draft(user_id)
        if draft and not draft.get('ad_added'):
            draft['text'] += f"\n\n{ad_text}"
            database.save_draft(user_id, draft['photo'], draft['text'], draft['document'], draft['channel'], 1)
            finalize_draft_update(chat_id, call.message.message_id, draft)
            bot.answer_callback_query(call.id, MESSAGES[lang]['ad_added'])

    elif call.data == "pub_now":
        draft = database.get_draft(user_id)
        if draft and core.publish_post_data(-1, draft['photo'], draft['text'], draft['document'], draft['channel']):
            database.record_published_post(draft['photo'], draft['text'], draft['document'], draft['channel'])
            database.clear_draft(user_id)
            bot.delete_message(chat_id, call.message.message_id)

    elif call.data == "pub_queue_menu": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_publish_queue_menu(call.message.message_id, "sc", lang))
    elif call.data == "back_to_draft": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_draft_markup(lang))
    elif call.data == "cancel_action": bot.delete_message(chat_id, call.message.message_id)

def finalize_draft_update(chat_id, message_id, draft):
    lang = get_user_lang(chat_id)
    doc_info = f"\n\n📄 <b>File:</b> Yes" if draft.get('document') else ""
    full_text = draft['text'] + doc_info
    try: bot.edit_message_text(full_text, chat_id, message_id, parse_mode='HTML', reply_markup=markups.get_draft_markup(lang))
    except:
        try: bot.edit_message_caption(full_text, chat_id, message_id, parse_mode='HTML', reply_markup=markups.get_draft_markup(lang))
        except: pass

def process_ad_step(message):
    lang = get_user_lang(message.from_user.id)
    if message.text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]: return
    utils.save_ad_text(message.text)
    bot.send_message(message.chat.id, MESSAGES[lang]['ad_saved'], reply_markup=markups.get_main_menu(lang))

def process_add_channel_step(message):
    lang = get_user_lang(message.from_user.id)
    if message.text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]: return
    new_ch = message.text.strip()
    if not new_ch.startswith('@'): new_ch = '@' + new_ch
    with open("channels.txt", "a", encoding="utf-8") as f: f.write(new_ch + "\n")
    bot.send_message(message.chat.id, MESSAGES[lang]['channel_added'], reply_markup=markups.get_main_menu(lang))

def save_edited_text(message, target_id, chat_id, is_queue=False, post_id=None):
    user_id = message.from_user.id
    lang = get_user_lang(user_id)
    if message.text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]: return
    formatted_text = utils.get_html_text(message)
    if is_queue:
        database.update_post_text(post_id, formatted_text)
        show_queue_page(chat_id, 0)
    else:
        draft = database.get_draft(user_id)
        if draft:
            bot.send_chat_action(chat_id, 'typing')
            draft['text'] = ai_generator.rewrite_post(formatted_text, "pro", lang)
            database.save_draft(user_id, draft['photo'], draft['text'], draft['document'], draft['channel'], 1 if draft.get('ad_added') else 0)
            send_draft_preview(chat_id, draft)

def process_custom_time(message, prefix, target_id, last_msg_id):
    chat_id, user_id = message.chat.id, message.from_user.id
    lang = get_user_lang(user_id)
    if message.text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]: return
    try:
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        now = datetime.now(tashkent_tz)
        parts = message.text.split()
        if len(parts) == 1:
            time_part = datetime.strptime(parts[0], "%H:%M")
            dt = now.replace(hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0)
            if dt < now: dt += timedelta(days=1)
        else:
            dt = datetime.strptime(message.text, "%d.%m %H:%M").replace(year=now.year)
            if dt < now: dt = dt.replace(year=now.year + 1)
        new_time = int(dt.timestamp())
        if prefix == "sc":
            draft = database.get_draft(user_id)
            if draft:
                database.add_to_queue(draft['photo'], draft['text'], draft['document'], draft['channel'], new_time)
                database.clear_draft(user_id)
                bot.delete_message(chat_id, last_msg_id)
        else:
            database.update_post_time(target_id, new_time)
            show_queue_page(chat_id, 0, last_msg_id)
        bot.send_message(chat_id, f"✅ {dt.strftime('%d.%m %H:%M')}", reply_markup=markups.get_main_menu(lang))
    except:
        bot.send_message(chat_id, f"❌ Format error! Use HH:MM or DD.MM HH:MM")

bot.polling(none_stop=True)
