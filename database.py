import sqlite3
import time
import os

# Используем абсолютный путь к БД
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "bot_data.db"))

def init_db():
    print(f"🗄️ Initializing database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Основная таблица очереди и постов
    c.execute('''CREATE TABLE IF NOT EXISTS queue
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  photo_id TEXT,
                  text TEXT,
                  document_id TEXT,
                  channel_id TEXT,
                  scheduled_time INTEGER,
                  status TEXT DEFAULT 'pending')''')
    
    # Таблица комментариев для анализа
    c.execute('''CREATE TABLE IF NOT EXISTS comments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_name TEXT,
                  text TEXT,
                  timestamp INTEGER)''')
                  
    # ТАБЛИЦА НАСТРОЕК (ДЛЯ ДОЛГОЙ ПАМЯТИ)
    c.execute('''CREATE TABLE IF NOT EXISTS user_settings
                 (user_id INTEGER PRIMARY KEY,
                  lang TEXT DEFAULT 'uz',
                  active_channel TEXT)''')
                  
    # ТАБЛИЦА ЧЕРНОВИКОВ (ЧТОБЫ НЕ ПРОПАДАЛИ ПРИ RESTART)
    c.execute('''CREATE TABLE IF NOT EXISTS drafts
                 (user_id INTEGER PRIMARY KEY,
                  photo_id TEXT,
                  text TEXT,
                  document_id TEXT,
                  channel_id TEXT,
                  ad_added INTEGER DEFAULT 0)''')
                  
    conn.commit()
    conn.close()

# --- ФУНКЦИИ ОЧЕРЕДИ ---

def add_to_queue(photo_id, text, document_id=None, channel_id=None, scheduled_time=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO queue (photo_id, text, document_id, channel_id, scheduled_time, status) VALUES (?, ?, ?, ?, ?, 'pending')", 
              (photo_id, text, document_id, channel_id, scheduled_time))
    conn.commit()
    conn.close()

def get_ready_posts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_time = int(time.time())
    c.execute('''SELECT id, photo_id, text, document_id, channel_id 
                 FROM queue 
                 WHERE status='pending' AND (scheduled_time IS NULL OR scheduled_time <= ?) 
                 ORDER BY scheduled_time ASC''', (current_time,))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_as_posted(post_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE queue SET status = 'posted' WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

def update_post_text(post_id, new_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE queue SET text = ? WHERE id = ?", (new_text, post_id))
    conn.commit()
    conn.close()

def update_post_time(post_id, new_time):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE queue SET scheduled_time = ? WHERE id = ?", (new_time, post_id))
    conn.commit()
    conn.close()

def get_all_pending():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, photo_id, text, document_id, channel_id, scheduled_time FROM queue WHERE status='pending' ORDER BY scheduled_time ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def delete_from_queue(post_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM queue WHERE id=?", (post_id,))
    conn.commit()
    conn.close()

def is_duplicate(document_id):
    """Проверяет, есть ли такой файл уже в базе (в очереди или опубликован)."""
    if not document_id: return False
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM queue WHERE document_id = ?", (document_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

def get_last_scheduled_time():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT scheduled_time FROM queue WHERE status='pending' AND scheduled_time IS NOT NULL ORDER BY scheduled_time DESC LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# --- ФУНКЦИИ НАСТРОЕК И ЧЕРНОВИКОВ (ДОЛГАЯ ПАМЯТЬ) ---

def set_user_setting(user_id, lang=None, channel=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if lang:
        c.execute("INSERT INTO user_settings (user_id, lang) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET lang=?", (user_id, lang, lang))
    if channel:
        c.execute("INSERT INTO user_settings (user_id, active_channel) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET active_channel=?", (user_id, channel, channel))
    conn.commit()
    conn.close()

def get_user_settings(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT lang, active_channel FROM user_settings WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row if row else ('uz', None)

def save_draft(user_id, photo_id, text, document_id, channel_id, ad_added=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO drafts (user_id, photo_id, text, document_id, channel_id, ad_added) 
                 VALUES (?, ?, ?, ?, ?, ?) 
                 ON CONFLICT(user_id) DO UPDATE SET 
                 photo_id=excluded.photo_id, text=excluded.text, 
                 document_id=excluded.document_id, channel_id=excluded.channel_id, 
                 ad_added=excluded.ad_added''', 
              (user_id, photo_id, text, document_id, channel_id, ad_added))
    conn.commit()
    conn.close()

def get_draft(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT photo_id, text, document_id, channel_id, ad_added FROM drafts WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'photo': row[0], 'text': row[1], 'document': row[2], 'channel': row[3], 'ad_added': bool(row[4])}
    return None

def clear_draft(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM drafts WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# --- СТАТИСТИКА И КОММЕНТАРИИ ---

def get_stats():
    import pytz
    from datetime import datetime
    import config
    
    # Считаем каналы
    channels_count = len(config.AVAILABLE_CHANNELS)
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            extra = [l for l in f.readlines() if l.strip()]
            channels_count += len(extra)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM queue")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM queue WHERE status='posted'")
    published = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM queue WHERE status='pending'")
    queue_count = c.fetchone()[0]
    tashkent_tz = pytz.timezone('Asia/Tashkent')
    today_start = int(datetime.now(tashkent_tz).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    c.execute("SELECT COUNT(*) FROM queue WHERE status='posted' AND scheduled_time >= ?", (today_start,))
    today = c.fetchone()[0]
    conn.close()
    return {'total': total, 'published': published, 'queue': queue_count, 'today': today, 'channels': channels_count}

def get_all_posts():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM queue")
    rows = c.fetchall()
    conn.close()
    return rows

def record_published_post(photo_id, text, document_id, channel_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    current_time = int(time.time())
    c.execute("INSERT INTO queue (photo_id, text, document_id, channel_id, scheduled_time, status) VALUES (?, ?, ?, ?, ?, 'posted')", 
              (photo_id, text, document_id, channel_id, current_time))
    conn.commit()
    conn.close()

def save_comment(user_name, text, timestamp):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO comments (user_name, text, timestamp) VALUES (?, ?, ?)", 
              (user_name, text, timestamp))
    conn.commit()
    conn.close()

def get_all_comments():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_name, text FROM comments ORDER BY timestamp ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def clear_comments():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM comments")
    conn.commit()
    conn.close()

init_db()
