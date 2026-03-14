import telebot
import config
import database
import os
import time
import re
from bot_instance import bot
from strings import MESSAGES

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
                title = re.sub(r'<[^>]+>', '', text).split('\n')[0][:50]
                for admin in getattr(config, 'ADMIN_IDS', []):
                    try: bot.send_message(admin, f"✅ <b>Автопостинг:</b> Опубликовано в {channel_id}!\n\n📝 <b>Пост:</b> <i>{title}...</i>", parse_mode='HTML') 
                    except: pass
        return True
    except Exception as e:
        print(f"❌ Ошибка публикации в {channel_id}: {e}")
        return False

def process_queue():
    """Функция без аргументов для планировщика"""
    posts = database.get_ready_posts()
    for post in posts:
        post_id, photo_id, text, document_id, channel_id = post
        target_channel = channel_id if channel_id else config.DEFAULT_CHANNEL
        publish_post_data(post_id, photo_id, text, document_id, target_channel, is_auto=True)

def show_stats(chat_id, channels_count, lang='uz'):
    stats = database.get_stats()
    text = MESSAGES[lang]['stats'].format(
        total=stats['total'],
        published=stats['published'],
        queue=stats['queue'],
        today=stats['today'],
        channels=channels_count
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
