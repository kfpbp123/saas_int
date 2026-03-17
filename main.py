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

# --- SCHEDULER (Global/Shared) ---
jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///jobs.sqlite')}
scheduler = BackgroundScheduler(jobstores=jobstores)
if not scheduler.get_job('queue_process'):
    scheduler.add_job(core.process_queue, 'interval', minutes=1, id='queue_process', replace_existing=True)
scheduler.start()

def get_user_lang(user_id):
    try:
        lang, _ = database.get_user_settings(user_id)
        return lang or 'uz'
    except:
        return 'uz'

def register_handlers(bot):
    bot_id = database.get_bot_id_by_token(bot.token)
    album_cache = {}
    user_states = {}
    admin_media_cache = {}

    def add_to_queue_multi(user_id, photo, text, doc, time_sched):
        user_channels = database.get_user_channels(user_id)
        if user_channels:
            for ch in user_channels:
                database.add_to_queue(photo, text, doc, f"@{ch.channel_username}", time_sched, owner_id=database.get_or_create_user(user_id).id, bot_id=bot_id)
        else:
            database.add_to_queue(photo, text, doc, config.DEFAULT_CHANNEL, time_sched, owner_id=database.get_or_create_user(user_id).id, bot_id=bot_id)

    # --- MIDDLEWARE (PRO CHECK) ---
    @bot.middleware_handler(update_types=['message'])
    def check_subscription(bot_instance, message):
        user_id = message.from_user.id
        lang = get_user_lang(user_id)
        
        if user_id in getattr(config, 'ADMIN_IDS', []): return
        if message.chat.type != 'private': return
        if message.text and message.text.startswith('/start'): return
        
        database.get_or_create_user(user_id, message.from_user.username)
        
        text = message.text or message.caption
        is_pro_action = False
        if text and text in [BUTTONS[lang]['create'], BUTTONS[lang]['ai_chat']]:
            is_pro_action = True
        
        if is_pro_action:
            if not database.check_pro_status(user_id):
                bot.send_message(message.chat.id, MESSAGES[lang]['not_pro'], 
                                 parse_mode='HTML', reply_markup=markups.get_pro_upgrade_markup(lang))
                return telebot.handler_backends.CancelHandler()

    def show_queue_page(chat_id, page, message_id=None):
        user_id = chat_id 
        lang = get_user_lang(user_id)
        posts = database.get_all_pending()
        if not posts:
            text = MESSAGES[lang]['queue_empty']
            if message_id:
                try: bot.delete_message(chat_id, message_id)
                except: pass
            bot.send_message(chat_id, text, parse_mode='HTML')
            return

        if page >= len(posts): page = len(posts) - 1
        if page < 0: page = 0
        post = posts[page]
        post_id, photo_id, text, doc_id, channel, time_sched = post
        
        msg_text = utils.format_queue_post(post, page + 1, len(posts))
        markup = markups.get_queue_manage_markup(post_id, page, lang)

        if message_id:
            try: bot.delete_message(chat_id, message_id)
            except: pass

        if photo_id:
            if ',' in photo_id:
                bot.send_media_group(chat_id, [telebot.types.InputMediaPhoto(m) for m in photo_id.split(',')])
                bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)
            else:
                if len(msg_text) <= 1024:
                    bot.send_photo(chat_id, photo_id, caption=msg_text, parse_mode='HTML', reply_markup=markup)
                else:
                    bot.send_photo(chat_id, photo_id)
                    bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)
        else:
            bot.send_message(chat_id, msg_text, parse_mode='HTML', reply_markup=markup)

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        if message.chat.type != 'private': return
        user_id = message.from_user.id
        lang = get_user_lang(user_id)
        user_states[message.chat.id] = None
        text = MESSAGES[lang]['welcome']
        bot.send_message(message.chat.id, text, reply_markup=markups.get_main_menu(lang), parse_mode='HTML')

    @bot.message_handler(commands=['admin'])
    def admin_panel(message):
        if message.from_user.id not in config.ADMIN_IDS: return
        bot.send_message(message.chat.id, "👑 <b>Admin Panel</b>", 
                         parse_mode='HTML', reply_markup=markups.get_admin_main_menu())

    def process_auto_post_delayed(chat_id, user_id, doc_id, file_unique_id, direct_text, lang):
        try:
            bot.send_message(chat_id, "🤖 Мод получен. Обработка и водяной знак...")
            
            cache = admin_media_cache.get(user_id, {})
            cache_text = cache.get('text', "")
            cache_photo = cache.get('photo_id')
            
            final_text = direct_text or cache_text or "Minecraft Mod"
            raw_photos = cache_photo
            
            if not database.check_user_limit(user_id, 'ai_gen'):
                bot.send_message(chat_id, MESSAGES[lang]['not_pro'], parse_mode='HTML', reply_markup=markups.get_pro_upgrade_markup(lang))
                return

            ai_text = ai_generator.generate_post(final_text, lang)
            if not ai_text or "REJECT" in ai_text.upper():
                bot.send_message(chat_id, "⏩ Ошибка ИИ или отказ.")
                return
            database.log_usage(user_id, 'ai_gen')

            final_photo_ids = []
            if raw_photos:
                photo_list = raw_photos.split(',')
                for p_id in photo_list:
                    try:
                        temp_in, temp_out = f"auto_in_{p_id}.jpg", f"auto_out_{p_id}.jpg"
                        file_info = bot.get_file(p_id)
                        with open(temp_in, 'wb') as f: f.write(bot.download_file(file_info.file_path))
                        watermarker.add_watermark(temp_in, temp_out)
                        with open(temp_out if os.path.exists(temp_out) else temp_in, 'rb') as f:
                            sent = bot.send_photo(chat_id, f, caption="🎨 Накладываю водяной знак...")
                            final_photo_ids.append(sent.photo[-1].file_id)
                            bot.delete_message(chat_id, sent.message_id)
                        if os.path.exists(temp_in): os.remove(temp_in)
                        if os.path.exists(temp_out): os.remove(temp_out)
                    except: final_photo_ids.append(p_id)

            final_photo_str = ",".join(final_photo_ids) if final_photo_ids else None
            
            new_time = core.get_next_schedule_time()
            u_obj = database.get_or_create_user(user_id)
            post_id = database.add_to_queue(final_photo_str, ai_text, doc_id, config.DEFAULT_CHANNEL, new_time, file_unique_id, owner_id=u_obj.id, bot_id=bot_id)
            database.log_usage(user_id, 'post_publish')
            
            time_str = datetime.fromtimestamp(new_time).strftime('%d.%m %H:%M')
            caption = f"{ai_text}\n\n✅ В очереди на {time_str}"
            markup = markups.get_queue_manage_markup(post_id, 0, lang)
            
            if final_photo_str and ',' in final_photo_str:
                bot.send_media_group(chat_id, [telebot.types.InputMediaPhoto(m) for m in final_photo_str.split(',')])
                bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=markup)
            elif final_photo_str:
                bot.send_photo(chat_id, final_photo_str, caption=caption[:1024], parse_mode='HTML', reply_markup=markup)
            else:
                bot.send_message(chat_id, caption, parse_mode='HTML', reply_markup=markup)

            if user_id in admin_media_cache: del admin_media_cache[user_id]
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка: {e}")

    @bot.message_handler(content_types=['text', 'photo', 'document', 'video', 'audio', 'voice'])
    def handle_text_photo_file(message):
        chat_id = message.chat.id
        user_id = message.from_user.id
        lang = get_user_lang(user_id)
        text = message.text if message.content_type == 'text' else message.caption

        if text: print(f"📩 [{chat_id}] Message: {text}")

        state_data = user_states.get(chat_id)
        is_creating = state_data and state_data.get('state') == 'creating_post'
        is_admin = user_id in getattr(config, 'ADMIN_IDS', [])

        if is_admin and message.chat.type == 'private':
            if is_creating and (message.document or message.video):
                doc_id = message.document.file_id if message.document else message.video.file_id
                draft = database.get_draft(user_id) or {'photo': None, 'text': "", 'document': None, 'channel': config.DEFAULT_CHANNEL}
                draft['document'] = doc_id
                database.save_draft(user_id, draft['photo'], draft['text'], doc_id, draft['channel'])
                user_states[chat_id] = None 
                bot.send_message(chat_id, "📎 Файл прикреплен к черновику!", reply_markup=markups.get_main_menu(lang))
                send_draft_preview(chat_id, draft)
                return

            if database.is_auto_post_on() and not is_creating:
                if message.content_type == 'text' and not message.document:
                    admin_media_cache[user_id] = admin_media_cache.get(user_id, {})
                    admin_media_cache[user_id].update({'text': text, 'time': time.time()})
                    print("📝 Текст админа сохранен")

                if message.photo:
                    admin_media_cache[user_id] = admin_media_cache.get(user_id, {})
                    current_photos = admin_media_cache[user_id].get('photo_id', "")
                    new_photo = message.photo[-1].file_id
                    if message.media_group_id:
                        if new_photo not in current_photos:
                            updated_photos = (current_photos + "," + new_photo) if current_photos else new_photo
                            admin_media_cache[user_id].update({'photo_id': updated_photos, 'time': time.time()})
                    else:
                        admin_media_cache[user_id].update({'photo_id': new_photo, 'time': time.time()})
                    print(f"🖼 Фото добавлено в кэш автопостинга (всего: {len(admin_media_cache[user_id].get('photo_id','').split(','))})")

                if (message.document or message.video):
                    doc_id = message.document.file_id if message.document else message.video.file_id
                    file_unique_id = message.document.file_unique_id if message.document else message.video.file_unique_id
                    if database.is_duplicate(file_unique_id):
                        bot.send_message(chat_id, "⏩ Мод уже есть в базе, пропускаю.")
                        return
                    threading.Timer(1.5, process_auto_post_delayed, args=[chat_id, user_id, doc_id, file_unique_id, text, lang]).start()
                    return

        if is_creating:
            if message.content_type == 'text':
                bot.send_chat_action(chat_id, 'typing')
                start_generation(chat_id, user_id, text, None)
                return
            elif message.photo:
                if not message.media_group_id:
                    start_generation(chat_id, user_id, message.caption, message.photo[-1].file_id)
                elif message.media_group_id not in album_cache:
                    album_cache[message.media_group_id] = []
                    threading.Timer(2.0, process_album_immediate, args=[message.media_group_id, chat_id, user_id]).start()
                if message.media_group_id: album_cache[message.media_group_id].append(message)
                return

        if message.chat.type in ['group', 'supergroup']:
            if text and not text.startswith('/'):
                database.save_comment(message.from_user.first_name, text, int(time.time()))
                print(f"💬 Сохранен комментарий от {message.from_user.first_name}: {text[:50]}...")
            return

        if text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]:
            user_states[chat_id] = None
            bot.send_message(chat_id, MESSAGES[lang]['ai_chat_off'], reply_markup=markups.get_main_menu(lang), parse_mode='HTML')
            return

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
                comments = database.get_all_comments()[-30:]
                comm_text = "\n".join([f"- {c[0]}: {c[1]}" for c in comments])
                context_msg = f"[Context: Bot for @lazikosmods. Queue: {stats['queue']} posts. Channel: {channel}. Comments:\n{comm_text or 'No'}] {message.text}"
                response = ai_generator.chat_with_ai(context_msg, lang)
                bot.send_message(chat_id, f"🤖 <b>AI:</b>\n\n{response}", parse_mode='HTML', reply_markup=markups.get_cancel_markup(lang))
                return
            elif state_data.get('state') == 'creating_post':
                user_states[chat_id] = None 
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
                user_channels = database.get_user_channels(user_id)
                bot.send_message(chat_id, f"📢 <b>{BUTTONS[lang]['channels']}:</b>", reply_markup=markups.get_user_channels_markup(user_channels, lang), parse_mode='HTML')
            elif text in [BUTTONS['uz']['queue'], BUTTONS['ru']['queue'], BUTTONS['en']['queue']]:
                bot.send_chat_action(chat_id, 'typing')
                show_queue_page(chat_id, 0)
            elif text in [BUTTONS['uz']['stats'], BUTTONS['ru']['stats'], BUTTONS['en']['stats']]:
                core.show_stats(chat_id, len(utils.get_channels()), lang, bot=bot)
            elif text in [BUTTONS['uz']['settings'], BUTTONS['ru']['settings'], BUTTONS['en']['settings']]:
                auto_p = database.is_auto_post_on()
                bot.send_message(chat_id, MESSAGES[lang]['settings'], reply_markup=markups.get_settings_menu(lang, auto_p), parse_mode='HTML')
            elif text in [BUTTONS['uz']['analyze'], BUTTONS['ru']['analyze'], BUTTONS['en']['analyze']]:
                bot.send_chat_action(chat_id, 'typing')
                msg = bot.send_message(chat_id, MESSAGES[lang]['analyzing'], parse_mode='HTML')
                threading.Thread(target=utils.animate_progress, args=(bot, chat_id, msg.message_id, MESSAGES[lang]['analyzing']), daemon=True).start()
                report = comments_analyzer.analyze_comments()
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(telebot.types.InlineKeyboardButton("🗑 Clear", callback_data="clear_comments_db"))
                bot.edit_message_text(report, chat_id, msg.message_id, parse_mode="HTML", reply_markup=markup)
            elif text in [BUTTONS['uz']['trends'], BUTTONS['ru']['trends'], BUTTONS['en']['trends']]:
                bot.send_chat_action(chat_id, 'typing')
                msg = bot.send_message(chat_id, MESSAGES[lang]['searching_trends'], parse_mode='HTML')
                threading.Thread(target=utils.animate_progress, args=(bot, chat_id, msg.message_id, MESSAGES[lang]['searching_trends']), daemon=True).start()
                trends = web_searcher.get_all_trends()
                if not trends:
                    bot.edit_message_text("⚠️ No trends found.", chat_id, msg.message_id)
                    return
                res_text = MESSAGES[lang]['trending_title']
                for i, item in enumerate(trends, 1):
                    icon = "🎬" if item['source'] == "YouTube" else "📦"
                    res_text += f"{i}. {icon} <a href='{item['url']}'>{item['title']}</a>\n"
                bot.edit_message_text(res_text, chat_id, msg.message_id, parse_mode='HTML', disable_web_page_preview=True)
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
        threading.Thread(target=utils.animate_progress, args=(bot, chat_id, msg.message_id, MESSAGES[lang]['generation_start']), daemon=True).start()
        
        if not database.check_user_limit(user_id, 'ai_gen'):
            bot.send_message(chat_id, MESSAGES[lang]['not_pro'], parse_mode='HTML', reply_markup=markups.get_pro_upgrade_markup(lang))
            bot.delete_message(chat_id, msg.message_id)
            return

        generated_text = ai_generator.generate_post(user_input or "Minecraft", persona=lang)
        database.log_usage(user_id, 'ai_gen')
        bot.delete_message(chat_id, msg.message_id)
        final_photo_ids = []
        if photo_id:
            bot.send_chat_action(chat_id, 'upload_photo')
            input_ids = photo_id.split(',') if is_album else [photo_id]
            for p_id in input_ids:
                try:
                    temp_in, temp_out = f"in_{chat_id}_{len(final_photo_ids)}.jpg", f"out_{chat_id}_{len(final_photo_ids)}.jpg"
                    file_info = bot.get_file(p_id)
                    with open(temp_in, 'wb') as f: f.write(bot.download_file(file_info.file_path))
                    watermarker.add_watermark(temp_in, temp_out)
                    with open(temp_out if os.path.exists(temp_out) else temp_in, 'rb') as f:
                        sent = bot.send_photo(chat_id, f, caption="🎨 Processing photo...")
                        final_photo_ids.append(sent.photo[-1].file_id)
                        bot.delete_message(chat_id, sent.message_id)
                    if os.path.exists(temp_in): os.remove(temp_in)
                    if os.path.exists(temp_out): os.remove(temp_out)
                except Exception as e:
                    print(f"⚠️ Error watermarking photo {p_id}: {e}")
                    final_photo_ids.append(p_id)
        final_photo_id_str = ",".join(final_photo_ids) if final_photo_ids else None
        draft = {'photo': final_photo_id_str, 'text': generated_text, 'document': None, 'ad_added': False, 'channel': utils.get_active_channel(user_id)}
        database.save_draft(user_id, final_photo_id_str, generated_text, None, draft['channel'])
        send_draft_preview(chat_id, draft)

    def send_draft_preview(chat_id, draft):
        lang = get_user_lang(chat_id)
        bot.send_chat_action(chat_id, 'typing')
        doc_info = f"\n\n📄 <b>File:</b> Yes" if draft.get('document') else ""
        
        user_channels = database.get_user_channels(chat_id)
        if user_channels:
            ch_list = ", ".join([f"@{c.channel_username}" for c in user_channels])
        else:
            ch_list = config.DEFAULT_CHANNEL
        ch_info = f"\n\n📢 <b>Channels:</b> {ch_list}"
        
        full_text = draft['text'] + doc_info + ch_info
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
        
        # --- ADMIN CALLBACKS ---
        if call.data.startswith('adm_') and user_id not in config.ADMIN_IDS:
            bot.answer_callback_query(call.id, "Access Denied")
            return

        if call.data == 'adm_main':
            bot.edit_message_text("👑 <b>Admin Panel</b>", chat_id, call.message.message_id, 
                                  parse_mode='HTML', reply_markup=markups.get_admin_main_menu())
        
        elif call.data == 'adm_stats':
            stats = database.get_global_stats()
            text = f"📊 <b>Global Stats:</b>\n\n" \
                   f"👤 Users: {stats['users']}\n" \
                   f"💎 PRO: {stats['pro']}\n" \
                   f"🤖 Bots: {stats['bots']}\n" \
                   f"📦 Posts: {stats['posts']}"
            bot.edit_message_text(text, chat_id, call.message.message_id, 
                                  parse_mode='HTML', reply_markup=markups.get_admin_main_menu())

        elif call.data.startswith('adm_users_'):
            page = int(call.data.replace('adm_users_', ''))
            users = database.get_all_users(limit=10, offset=page*10)
            bot.edit_message_text("👤 <b>Users List:</b>", chat_id, call.message.message_id, 
                                  parse_mode='HTML', reply_markup=markups.get_admin_users_menu(users, page))

        elif call.data.startswith('adm_user_view_'):
            tg_id = int(call.data.replace('adm_user_view_', ''))
            user = database.get_user_by_tg_id(tg_id)
            if user:
                text = f"👤 <b>User Info:</b>\n" \
                       f"ID: <code>{user.telegramId}</code>\n" \
                       f"Username: @{user.username}\n" \
                       f"Tier: {user.subscription_tier}\n" \
                       f"Expires: {user.proExpiresAt}"
                bot.edit_message_text(text, chat_id, call.message.message_id, 
                                      parse_mode='HTML', reply_markup=markups.get_admin_user_manage_markup(tg_id))

        elif call.data.startswith('adm_set_tier_'):
            parts = call.data.split('_')
            tier, tg_id = parts[3], int(parts[4])
            database.set_user_tier(tg_id, tier)
            bot.answer_callback_query(call.id, f"✅ Tier set to {tier}")
            user = database.get_user_by_tg_id(tg_id)
            text = f"👤 <b>User Info:</b>\n" \
                   f"ID: <code>{user.telegramId}</code>\n" \
                   f"Username: @{user.username}\n" \
                   f"Tier: {user.subscription_tier}\n" \
                   f"Expires: {user.proExpiresAt}"
            bot.edit_message_text(text, chat_id, call.message.message_id, 
                                  parse_mode='HTML', reply_markup=markups.get_admin_user_manage_markup(tg_id))

        elif call.data == 'adm_bots':
            bots = database.get_all_bots()
            bot.edit_message_text("🤖 <b>Bot Instances:</b>", chat_id, call.message.message_id, 
                                  parse_mode='HTML', reply_markup=markups.get_admin_bots_menu(bots))

        elif call.data.startswith('adm_bot_toggle_'):
            bot_id = int(call.data.replace('adm_bot_toggle_', ''))
            database.toggle_bot_status(bot_id)
            bots = database.get_all_bots()
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_admin_bots_menu(bots))

        elif call.data == 'adm_bot_add':
            msg = bot.send_message(chat_id, "🔑 <b>Enter Bot Token:</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, process_adm_bot_add)

        elif call.data == 'adm_scanner':
            channels = database.get_whitelist_channels()
            bot.edit_message_text("🔎 <b>Scanner Whitelist:</b>", chat_id, call.message.message_id, 
                                  parse_mode='HTML', reply_markup=markups.get_admin_scanner_menu(channels))

        elif call.data.startswith('adm_scan_del_'):
            ch = call.data.replace('adm_scan_del_', '')
            database.delete_whitelist_channel(ch)
            channels = database.get_whitelist_channels()
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_admin_scanner_menu(channels))

        elif call.data == 'adm_scan_add':
            msg = bot.send_message(chat_id, "➕ <b>Enter Channel Username (@chan):</b>", parse_mode='HTML')
            bot.register_next_step_handler(msg, process_adm_scan_add)
        
        # --- END ADMIN CALLBACKS ---

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
        
        elif call.data.startswith('del_ch_'):
            ch_id = int(call.data.replace('del_ch_', ''))
            database.delete_user_channel(user_id, ch_id)
            user_channels = database.get_user_channels(user_id)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, 
                                          reply_markup=markups.get_user_channels_markup(user_channels, lang))
            bot.answer_callback_query(call.id, "✅ Deleted")

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
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_settings_menu(lang, auto_p))
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
                        add_to_queue_multi(user_id, draft['photo'], draft['text'], draft['document'], new_time)
                        database.log_usage(user_id, 'post_publish')
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
                if post and core.publish_post_data(post[0], post[1], post[2], post[3], post[4] or config.DEFAULT_CHANNEL, bot=bot):
                    show_queue_page(chat_id, 0, call.message.message_id)
            elif action == 'time':
                bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_publish_queue_menu(val, "qt", lang))

        elif call.data == "buy_pro":
            bot.send_message(chat_id, "💳 <b>Transfer $9.99 to:</b>\n<code>4400 1234 5678 9010</code>\n\n" + MESSAGES[lang]['enter_ad'].replace("ad", "receipt"), parse_mode='HTML', reply_markup=markups.get_cancel_markup(lang))
            bot.register_next_step_handler(call.message, process_receipt)

        elif call.data.startswith("adm_pay_ok_"):
            parts = call.data.split("_")
            pay_id, user_tg_id = int(parts[3]), int(parts[4])
            success, tg_id = database.approve_payment(pay_id)
            if success:
                bot.answer_callback_query(call.id, "✅ User is now PRO!")
                bot.edit_message_caption(call.message.caption + "\n\n✅ APPROVED", chat_id, call.message.message_id)
                try: bot.send_message(user_tg_id, "💎 <b>PRO Activated!</b>\nYou now have unlimited access to all features for 30 days.", parse_mode='HTML')
                except: pass

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
                add_to_queue_multi(user_id, draft['photo'], draft['text'], draft['document'], new_time)
                database.log_usage(user_id, 'post_publish')
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
            if draft:
                user_channels = database.get_user_channels(user_id)
                success = False
                if user_channels:
                    for ch in user_channels:
                        target = f"@{ch.channel_username}"
                        if core.publish_post_data(-1, draft['photo'], draft['text'], draft['document'], target, bot=bot):
                            database.record_published_post(draft['photo'], draft['text'], draft['document'], target)
                            success = True
                else:
                    target = config.DEFAULT_CHANNEL
                    if core.publish_post_data(-1, draft['photo'], draft['text'], draft['document'], target, bot=bot):
                        database.record_published_post(draft['photo'], draft['text'], draft['document'], target)
                        success = True
                if success:
                    database.clear_draft(user_id)
                    bot.delete_message(chat_id, call.message.message_id)
                    bot.send_message(chat_id, "✅ Published!", reply_markup=markups.get_main_menu(lang))

        elif call.data == "pub_queue_menu": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_publish_queue_menu(call.message.message_id, "sc", lang))
        elif call.data == "back_to_draft": bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markups.get_draft_markup(lang))
        elif call.data == "cancel_action": bot.delete_message(chat_id, call.message.message_id)

    def process_receipt(message):
        lang = get_user_lang(message.from_user.id)
        if message.text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]:
            bot.send_message(message.chat.id, "❌ Cancelled", reply_markup=markups.get_main_menu(lang))
            return
        if not message.photo:
            bot.send_message(message.chat.id, "🖼 Please send a PHOTO of your receipt.")
            bot.register_next_step_handler(message, process_receipt)
            return
        file_id = message.photo[-1].file_id
        amount = 9.99
        payment_id = database.create_manual_payment(message.from_user.id, amount, file_id)
        bot.send_message(message.chat.id, MESSAGES[lang]['payment_sent'], parse_mode='HTML', reply_markup=markups.get_main_menu(lang))
        for admin_id in getattr(config, 'ADMIN_IDS', []):
            try:
                markup = telebot.types.InlineKeyboardMarkup()
                markup.add(telebot.types.InlineKeyboardButton("✅ Approve", callback_data=f"adm_pay_ok_{payment_id}_{message.from_user.id}"))
                bot.send_photo(admin_id, file_id, caption=f"💸 <b>New Payment Request!</b>\nUser: {message.from_user.first_name} (@{message.from_user.username})\nAmount: ${amount}", parse_mode='HTML', reply_markup=markup)
            except: pass

    def finalize_draft_update(chat_id, message_id, draft):
        lang = get_user_lang(chat_id)
        doc_info = f"\n\n📄 <b>File:</b> Yes" if draft.get('document') else ""
        
        user_channels = database.get_user_channels(chat_id)
        if user_channels:
            ch_list = ", ".join([f"@{c.channel_username}" for c in user_channels])
        else:
            ch_list = config.DEFAULT_CHANNEL
        ch_info = f"\n\n📢 <b>Channels:</b> {ch_list}"
        
        full_text = draft['text'] + doc_info + ch_info
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
        user_id = message.from_user.id
        if message.text in [BUTTONS['uz']['cancel'], BUTTONS['ru']['cancel'], BUTTONS['en']['cancel']]:
            bot.send_message(message.chat.id, "❌ Cancelled", reply_markup=markups.get_main_menu(lang))
            return
        new_ch = message.text.strip()
        if not new_ch.startswith('@'): new_ch = '@' + new_ch
        database.add_user_channel(user_id, new_ch)
        bot.send_message(message.chat.id, MESSAGES[lang]['channel_added'], reply_markup=markups.get_main_menu(lang))
        user_channels = database.get_user_channels(user_id)
        bot.send_message(message.chat.id, f"📢 <b>{BUTTONS[lang]['channels']}:</b>", reply_markup=markups.get_user_channels_markup(user_channels, lang), parse_mode='HTML')

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
                    add_to_queue_multi(user_id, draft['photo'], draft['text'], draft['document'], new_time)
                    database.log_usage(user_id, 'post_publish')
                    database.clear_draft(user_id)
                    bot.delete_message(chat_id, last_msg_id)
            else:
                database.update_post_time(target_id, new_time)
                show_queue_page(chat_id, 0, last_msg_id)
            bot.send_message(chat_id, f"✅ {dt.strftime('%d.%m %H:%M')}", reply_markup=markups.get_main_menu(lang))
        except:
            bot.send_message(chat_id, f"❌ Format error! Use HH:MM or DD.MM HH:MM")

    def process_adm_bot_add(message):
        if message.from_user.id not in config.ADMIN_IDS: return
        token = message.text.strip()
        try:
            temp_bot = telebot.TeleBot(token)
            me = temp_bot.get_me()
            database.register_bot_instance(message.from_user.id, token, me.username)
            bot.send_message(message.chat.id, f"✅ Bot @{me.username} registered!")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Error: {e}")

    def process_adm_scan_add(message):
        if message.from_user.id not in config.ADMIN_IDS: return
        ch = message.text.strip()
        database.add_whitelist_channel(ch)
        bot.send_message(message.chat.id, f"✅ Channel {ch} added to whitelist!")
