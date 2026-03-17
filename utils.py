import pytz
from datetime import datetime, timedelta
import os
import re
import csv
import time
import config
import database

def animate_progress(bot, chat_id, message_id, base_text):
    """Анимирует многоточие для эффекта загрузки"""
    frames = ["⏳", "⏳.", "⏳..", "⏳..."]
    for _ in range(3): # 3 цикла анимации
        for frame in frames:
            try:
                bot.edit_message_text(f"{base_text}\n\n{frame}", chat_id, message_id, parse_mode='HTML')
                time.sleep(0.5)
            except:
                return # Если сообщение удалено или ошибка

def get_time_greeting():
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    hour = datetime.now(tashkent_tz).hour
    if hour < 6: return "Доброй ночи"
    elif hour < 12: return "Доброе утро"
    elif hour < 18: return "Добрый день"
    else: return "Добрый вечер"

def format_queue_post(post, index, total):
    post_id, photo_id, text, doc_id, channel, time_sched = post
    
    attachments = []
    if photo_id:
        if ',' in photo_id: attachments.append(f"🖼 Альбом ({len(photo_id.split(','))} фото)")
        else: attachments.append("🖼 Фото")
    
    file_status = "✅ Есть" if doc_id else "❌ Нет"
    
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    if time_sched:
        dt = datetime.fromtimestamp(time_sched, tashkent_tz)
        now = datetime.now(tashkent_tz)
        if dt.date() == now.date(): time_str = f"Сегодня в {dt.strftime('%H:%M')}"
        elif dt.date() == (now + timedelta(days=1)).date(): time_str = f"Завтра в {dt.strftime('%H:%M')}"
        else: time_str = dt.strftime('%d.%m.%Y %H:%M')
    else:
        time_str = "Время не задано"

    return f"""📋 <b>Пост {index} из {total}</b>
━━━━━━━━━━━━━
🆔 ID: <code>{post_id}</code>
⏳ <b>Время:</b> {time_str}
📢 <b>Канал:</b> {channel or config.DEFAULT_CHANNEL}
📄 <b>Файл:</b> {file_status}
🖼 <b>Медиа:</b> {", ".join(attachments) if attachments else "Нет"}
━━━━━━━━━━━━━

{text}"""

def get_html_text(message):
    """Конвертирует текст сообщения Telegram с сущностями (bold, italic и т.д.) в HTML."""
    if not message.entities:
        return message.text

    text = message.text
    entities = sorted(message.entities, key=lambda e: e.offset, reverse=True)
    for e in entities:
        start = e.offset
        end = e.offset + e.length
        tag = None
        if e.type == 'bold': tag = 'b'
        elif e.type == 'italic': tag = 'i'
        elif e.type == 'code': tag = 'code'
        elif e.type == 'pre': tag = 'pre'
        elif e.type == 'text_link': 
            text = text[:start] + f'<a href="{e.url}">' + text[start:end] + '</a>' + text[end:]
            continue
        
        if tag:
            text = text[:start] + f'<{tag}>' + text[start:end] + f'</{tag}>' + text[end:]
    return text

def get_channels():
    channels = config.AVAILABLE_CHANNELS.copy()
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            extra_channels = [line.strip() for line in f.readlines() if line.strip()]
            for ch in extra_channels:
                if ch not in channels: channels.append(ch)
    return channels

def get_active_channel(user_id):
    _, channel = database.get_user_settings(user_id)
    return channel or config.DEFAULT_CHANNEL

def get_active_persona(user_id):
    lang, _ = database.get_user_settings(user_id)
    return lang

def save_ad_text(text):
    with open("ad.txt", "w", encoding="utf-8") as f: f.write(text)

def get_ad_text():
    if os.path.exists("ad.txt"):
        with open("ad.txt", "r", encoding="utf-8") as f: return f.read()
    return ""

def generate_csv_export():
    posts = database.get_all_posts()
    if not posts: return None, None
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    filename = f"posts_export_{datetime.now(tashkent_tz).strftime('%Y%m%d_%H%M%S')}.csv"
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['ID', 'Канал', 'Текст', 'Статус', 'Время', 'Медиа'])
        for p in posts:
            time_str = datetime.fromtimestamp(p[5], tashkent_tz).strftime('%d.%m.%Y %H:%M') if p[5] else "—"
            writer.writerow([p[0], p[4], p[2], p[6], time_str, "Да" if p[1] or p[3] else "Нет"])
    return filename, posts
