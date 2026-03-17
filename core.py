import telebot
import config
import database
import os
import time
import re
from strings import MESSAGES

def publish_post_data(post_id, photo_id, text, document_id, channel_id, is_auto=False, bot=None):
    if bot is None:
        print("⚠️ No bot provided for publish_post_data")
        return False
        
    try:
        sent_msg = None
        if photo_id:
            if ',' in photo_id:
                ids = photo_id.split(',')
                media = [telebot.types.InputMediaPhoto(media=pid, caption=text if i==0 and len(text)<=1024 else None, parse_mode='HTML') for i, pid in enumerate(ids)]
                sent_msg = bot.send_media_group(channel_id, media)[0] # Берем первое сообщение из группы
                if len(text) > 1024:
                    bot.send_message(channel_id, text, parse_mode='HTML')
            else:
                if len(text) <= 1024:
                    sent_msg = bot.send_photo(channel_id, photo_id, caption=text, parse_mode='HTML')
                else:
                    bot.send_photo(channel_id, photo_id)
                    sent_msg = bot.send_message(channel_id, text, parse_mode='HTML')
        else:
            sent_msg = bot.send_message(channel_id, text, parse_mode='HTML')

        if document_id: bot.send_document(channel_id, document_id)

        if post_id != -1 and sent_msg:
            # Сохраняем статус и ID сообщения для аналитики
            database.mark_as_posted(post_id, sent_msg.message_id)
            if is_auto:
                title = re.sub(r'<[^>]+>', '', text).split('\n')[0][:50]
                for admin in getattr(config, 'ADMIN_IDS', []):
                    try: bot.send_message(admin, f"✅ <b>Автопостинг:</b> Опубликовано в {channel_id}!\n\n📝 <b>Пост:</b> <i>{title}...</i>", parse_mode='HTML') 
                    except: pass
        return True
    except Exception as e:
        print(f"❌ Ошибка публикации в {channel_id}: {e}")
        return False

def update_all_post_views():
    """
    Проходит по последним 50 постам в базе и обновляет просмотры (через Telegram API).
    """
    import launcher
    db = database.SessionLocal()
    try:
        posts = db.query(database.Queue).filter(database.Queue.status == 'posted', database.Queue.message_id != None).order_by(database.Queue.id.desc()).limit(50).all()
        for p in posts:
            bot = launcher.ACTIVE_BOTS.get(p.bot_id)
            if bot:
                try:
                    # В Telegram API боты не могут просто запросить 'views' через API, 
                    # но они могут 'переслать' сообщение самим себе, и в объекте Message будет поле views.
                    forwarded = bot.forward_message(getattr(config, 'ADMIN_IDS', [0])[0], p.channel_id, p.message_id, disable_notification=True)
                    if forwarded and forwarded.views:
                        # Обновляем или создаем запись в аналитике
                        anal = db.query(database.PostAnalytics).filter(database.PostAnalytics.post_id == p.id).first()
                        if not anal:
                            anal = database.PostAnalytics(post_id=p.id)
                            db.add(anal)
                        anal.views = forwarded.views
                        db.commit()
                        # Удаляем пересланное сообщение, чтобы не спамить админу
                        bot.delete_message(forwarded.chat.id, forwarded.message_id)
                except Exception as e:
                    print(f"⚠️ Error updating views for post {p.id}: {e}")
    finally:
        db.close()

def process_queue():
    """Функция без аргументов для планировщика. Теперь она мульти-ботовая."""
    import launcher
    posts = database.get_ready_posts()
    for post in posts:
        post_id, photo_id, text, document_id, channel_id, bot_id = post
        
        # Находим нужный инстанс бота
        bot = launcher.ACTIVE_BOTS.get(bot_id)
        
        # Если бота нет в памяти (например, только что добавили), попробуем создать временный
        if not bot:
            token = database.get_bot_token_by_id(bot_id)
            if token:
                bot = telebot.TeleBot(token)
                launcher.ACTIVE_BOTS[bot_id] = bot
        
        if bot:
            target_channel = channel_id if channel_id else config.DEFAULT_CHANNEL
            publish_post_data(post_id, photo_id, text, document_id, target_channel, is_auto=True, bot=bot)
        else:
            print(f"⚠️ Could not find bot instance for bot_id: {bot_id}")

def show_stats(chat_id, channels_count, lang='uz', bot=None):
    if bot:
        stats = database.get_stats()
        usage_info = database.get_user_usage_info(chat_id)
        
        text = MESSAGES[lang]['stats'].format(
            total=stats['total'],
            published=stats['published'],
            queue=stats['queue'],
            today=stats['today'],
            channels=channels_count,
            tier=usage_info['tier'],
            used=usage_info['used'],
            limit=usage_info['limit']
        )
        bot.send_message(chat_id, text, parse_mode='HTML')

def get_next_schedule_time():
    """Рассчитывает время для следующего поста в умной очереди (+8 часов от последнего)."""
    try:
        last_time = database.get_last_scheduled_time()
        interval = getattr(config, 'SMART_QUEUE_INTERVAL_HOURS', 8)
        now = int(time.time())
        
        if not last_time or last_time < now:
            return now + 3600 # Через час, если очередь пуста
        
        return last_time + (interval * 3600)
    except Exception as e:
        print(f"⚠️ Ошибка при расчете времени: {e}")
        return int(time.time()) + 3600
