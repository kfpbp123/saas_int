from sqlalchemy import create_all, create_engine, Column, Integer, BigInteger, String, Boolean, Float, DateTime, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
import time
from datetime import datetime
import config
import enum

# SQLAlchemy Setup
DATABASE_URL = getattr(config, 'DATABASE_URL', None)
if not DATABASE_URL:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'bot_data.db')}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELS ---

class PaymentStatus(enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class User(Base):
    __tablename__ = "User" # Open SaaS expects "User"
    id = Column(Integer, primary_key=True, index=True)
    telegramId = Column(BigInteger, unique=True, index=True)
    username = Column(String(255))
    isPro = Column(Boolean, default=False)
    subscription_tier = Column(String(50), default='free') # 'free', 'pro', 'business'
    proExpiresAt = Column(DateTime, nullable=True)
    createdAt = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    manualPayments = relationship("ManualPayment", back_populates="user")
    queuePosts = relationship("Queue", back_populates="owner")
    botInstances = relationship("BotInstance", back_populates="owner")
    channels = relationship("UserChannel", back_populates="user")

class UserChannel(Base):
    __tablename__ = "user_channels"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("User.id"))
    channel_username = Column(String(255))
    is_default = Column(Boolean, default=True)

    user = relationship("User", back_populates="channels")

class BotInstance(Base):
    __tablename__ = "bot_instances"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("User.id"))
    token = Column(String(255), unique=True)
    bot_username = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    createdAt = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="botInstances")
    queuePosts = relationship("Queue", back_populates="bot_ref")

class ManualPayment(Base):
    __tablename__ = "ManualPayment"
    id = Column(Integer, primary_key=True, index=True)
    userId = Column(Integer, ForeignKey("User.id"))
    amount = Column(Float)
    receiptUrl = Column(String, nullable=True)
    status = Column(String, default="PENDING") # Use string for simplicity with Enum
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="manualPayments")

class Queue(Base):
    __tablename__ = "queue"
    id = Column(Integer, primary_key=True, index=True)
    photo_id = Column(Text, nullable=True)
    text = Column(Text, nullable=True)
    document_id = Column(Text, nullable=True)
    channel_id = Column(Text, nullable=True)
    message_id = Column(BigInteger, nullable=True) # ID сообщения в канале
    scheduled_time = Column(Integer, nullable=True)
    status = Column(String, default='pending')
    file_unique_id = Column(String, unique=True, nullable=True)
    owner_id = Column(Integer, ForeignKey("User.id"), nullable=True)
    bot_id = Column(Integer, ForeignKey("bot_instances.id"), nullable=True)
    
    owner = relationship("User", back_populates="queuePosts")
    bot_ref = relationship("BotInstance", back_populates="queuePosts")
    analytics = relationship("PostAnalytics", back_populates="post")

class PostAnalytics(Base):
    __tablename__ = "post_analytics"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("queue.id"))
    views = Column(Integer, default=0)
    updatedAt = Column(DateTime, onupdate=datetime.utcnow)

    post = relationship("Queue", back_populates="analytics")

class GlobalSetting(Base):
    __tablename__ = "global_settings"
    key = Column(String, primary_key=True)
    value = Column(String)

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String)
    text = Column(Text)
    timestamp = Column(Integer)

class UserSetting(Base):
    __tablename__ = "user_settings"
    user_id = Column(BigInteger, primary_key=True)
    lang = Column(String, default='uz')
    active_channel = Column(String, nullable=True)

class Draft(Base):
    __tablename__ = "drafts"
    user_id = Column(BigInteger, primary_key=True)
    photo_id = Column(Text, nullable=True)
    text = Column(Text, nullable=True)
    document_id = Column(Text, nullable=True)
    channel_id = Column(Text, nullable=True)
    ad_added = Column(Integer, default=0)

class ScannerConfig(Base):
    __tablename__ = "scanner_config"
    id = Column(Integer, primary_key=True)
    channel_username = Column(String(255), unique=True)
    is_active = Column(Boolean, default=True)

class UsageLog(Base):
    __tablename__ = "usage_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("User.id"))
    action_type = Column(String(50)) # 'ai_gen', 'post_publish'
    createdAt = Column(DateTime, default=datetime.utcnow)

def init_db():
    print(f"🗄️ Initializing database with SQLAlchemy: {DATABASE_URL}")
    Base.metadata.create_all(bind=engine)

def get_whitelist_channels():
    db = SessionLocal()
    try:
        channels = db.query(ScannerConfig).filter(ScannerConfig.is_active == True).all()
        return [c.channel_username for c in channels]
    finally:
        db.close()

def add_whitelist_channel(username):
    db = SessionLocal()
    try:
        username = username.replace('@', '').lower()
        if not db.query(ScannerConfig).filter(ScannerConfig.channel_username == username).first():
            db.add(ScannerConfig(channel_username=username))
            db.commit()
    finally:
        db.close()

def delete_whitelist_channel(username):
    db = SessionLocal()
    try:
        username = username.replace('@', '').lower()
        db.query(ScannerConfig).filter(ScannerConfig.channel_username == username).delete()
        db.commit()
    finally:
        db.close()

# --- BOT INSTANCE HELPERS ---

def register_bot_instance(user_id, token, username=None):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == user_id).first()
        if not user:
            user = User(telegramId=user_id)
            db.add(user)
            db.commit()
            db.refresh(user)
        
        bot_inst = db.query(BotInstance).filter(BotInstance.token == token).first()
        if not bot_inst:
            bot_inst = BotInstance(owner_id=user.id, token=token, bot_username=username)
            db.add(bot_inst)
        else:
            bot_inst.bot_username = username
            bot_inst.is_active = True
        db.commit()
        db.refresh(bot_inst)
        return bot_inst
    finally:
        db.close()

def get_active_bots():
    db = SessionLocal()
    try:
        return db.query(BotInstance).filter(BotInstance.is_active == True).all()
    finally:
        db.close()

def get_ready_posts():
    db = SessionLocal()
    try:
        current_time = int(time.time())
        posts = db.query(Queue).filter(Queue.status == 'pending', Queue.scheduled_time <= current_time).all()
        return [(p.id, p.photo_id, p.text, p.document_id, p.channel_id, p.bot_id) for p in posts]
    finally:
        db.close()

def mark_as_posted(post_id, message_id=None):
    db = SessionLocal()
    try:
        db.query(Queue).filter(Queue.id == post_id).update({
            Queue.status: 'posted',
            Queue.message_id: message_id
        })
        db.commit()
    finally:
        db.close()

def get_bot_token_by_id(bot_id):
    db = SessionLocal()
    try:
        bot_inst = db.query(BotInstance).filter(BotInstance.id == bot_id).first()
        return bot_inst.token if bot_inst else None
    finally:
        db.close()

def get_bot_id_by_token(token):
    db = SessionLocal()
    try:
        bot_inst = db.query(BotInstance).filter(BotInstance.token == token).first()
        return bot_inst.id if bot_inst else None
    finally:
        db.close()

# --- DB HELPERS ---

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

# --- COMPATIBILITY FUNCTIONS ---

def add_to_queue(photo_id, text, document_id=None, channel_id=None, scheduled_time=None, file_unique_id=None, owner_id=None, bot_id=None):
    db = SessionLocal()
    try:
        new_post = Queue(
            photo_id=photo_id,
            text=text,
            document_id=document_id,
            channel_id=channel_id,
            scheduled_time=scheduled_time,
            file_unique_id=file_unique_id,
            owner_id=owner_id,
            bot_id=bot_id
        )
        db.add(new_post)
        db.commit()
        db.refresh(new_post)
        return new_post.id
    finally:
        db.close()

def get_all_pending():
    db = SessionLocal()
    try:
        posts = db.query(Queue).filter(Queue.status == 'pending').order_by(Queue.scheduled_time.asc()).all()
        return [(p.id, p.photo_id, p.text, p.document_id, p.channel_id, p.scheduled_time) for p in posts]
    finally:
        db.close()

def delete_from_queue(post_id):
    db = SessionLocal()
    try:
        post = db.query(Queue).filter(Queue.id == post_id).first()
        if post:
            deleted_time = post.scheduled_time
            db.delete(post)
            db.commit()
            
            # Smart Shift logic
            if deleted_time:
                interval = getattr(config, 'SMART_QUEUE_INTERVAL_HOURS', 6) * 3600
                db.query(Queue).filter(Queue.status == 'pending', Queue.scheduled_time > deleted_time).\
                    update({Queue.scheduled_time: Queue.scheduled_time - interval}, synchronize_session=False)
                db.commit()
    finally:
        db.close()

def update_post_text(post_id, new_text):
    db = SessionLocal()
    try:
        db.query(Queue).filter(Queue.id == post_id).update({Queue.text: new_text})
        db.commit()
    finally:
        db.close()

def update_post_time(post_id, new_time):
    db = SessionLocal()
    try:
        db.query(Queue).filter(Queue.id == post_id).update({Queue.scheduled_time: new_time})
        db.commit()
    finally:
        db.close()

def is_duplicate(file_unique_id):
    if not file_unique_id: return False
    db = SessionLocal()
    try:
        res = db.query(Queue).filter(Queue.file_unique_id == file_unique_id).first()
        return res is not None
    finally:
        db.close()

def get_last_scheduled_time():
    db = SessionLocal()
    try:
        res = db.query(Queue).filter(Queue.status == 'pending', Queue.scheduled_time != None).\
            order_by(Queue.scheduled_time.desc()).first()
        return res.scheduled_time if res else None
    finally:
        db.close()

# --- SETTINGS & DRAFTS ---

def set_global_setting(key, value):
    db = SessionLocal()
    try:
        setting = db.query(GlobalSetting).filter(GlobalSetting.key == key).first()
        if setting:
            setting.value = str(value)
        else:
            db.add(GlobalSetting(key=key, value=str(value)))
        db.commit()
    finally:
        db.close()

def get_global_setting(key, default='0'):
    db = SessionLocal()
    try:
        setting = db.query(GlobalSetting).filter(GlobalSetting.key == key).first()
        return setting.value if setting else default
    finally:
        db.close()

def is_auto_post_on():
    return get_global_setting('auto_post_enabled') == '1'

def get_user_settings(user_id):
    db = SessionLocal()
    try:
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if setting:
            return setting.lang, setting.active_channel
        return 'uz', None
    finally:
        db.close()

def set_user_setting(user_id, lang=None, channel=None):
    db = SessionLocal()
    try:
        setting = db.query(UserSetting).filter(UserSetting.user_id == user_id).first()
        if not setting:
            setting = UserSetting(user_id=user_id)
            db.add(setting)
        if lang: setting.lang = lang
        if channel: setting.active_channel = channel
        db.commit()
    finally:
        db.close()

def save_draft(user_id, photo_id, text, document_id, channel_id, ad_added=0):
    db = SessionLocal()
    try:
        draft = db.query(Draft).filter(Draft.user_id == user_id).first()
        if not draft:
            draft = Draft(user_id=user_id)
            db.add(draft)
        draft.photo_id = photo_id
        draft.text = text
        draft.document_id = document_id
        draft.channel_id = channel_id
        draft.ad_added = ad_added
        db.commit()
    finally:
        db.close()

def get_draft(user_id):
    db = SessionLocal()
    try:
        row = db.query(Draft).filter(Draft.user_id == user_id).first()
        if row:
            return {'photo': row.photo_id, 'text': row.text, 'document': row.document_id, 'channel': row.channel_id, 'ad_added': bool(row.ad_added)}
        return None
    finally:
        db.close()

def clear_draft(user_id):
    db = SessionLocal()
    try:
        db.query(Draft).filter(Draft.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()

# --- STATS & COMMENTS ---

def get_stats():
    import pytz
    from datetime import datetime
    import config
    
    channels_count = len(config.AVAILABLE_CHANNELS)
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            extra = [l for l in f.readlines() if l.strip()]
            channels_count += len(extra)

    db = SessionLocal()
    try:
        total = db.query(Queue).count()
        published = db.query(Queue).filter(Queue.status == 'posted').count()
        queue_count = db.query(Queue).filter(Queue.status == 'pending').count()
        
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        today_start = int(datetime.now(tashkent_tz).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        today = db.query(Queue).filter(Queue.status == 'posted', Queue.scheduled_time >= today_start).count()
        
        return {'total': total, 'published': published, 'queue': queue_count, 'today': today, 'channels': channels_count}
    finally:
        db.close()

def record_published_post(photo_id, text, document_id, channel_id):
    db = SessionLocal()
    try:
        current_time = int(time.time())
        new_post = Queue(photo_id=photo_id, text=text, document_id=document_id, channel_id=channel_id, scheduled_time=current_time, status='posted')
        db.add(new_post)
        db.commit()
    finally:
        db.close()

def save_comment(user_name, text, timestamp):
    db = SessionLocal()
    try:
        new_comment = Comment(user_name=user_name, text=text, timestamp=timestamp)
        db.add(new_comment)
        db.commit()
    finally:
        db.close()

def get_all_comments():
    db = SessionLocal()
    try:
        rows = db.query(Comment).order_by(Comment.timestamp.asc()).all()
        return [(r.user_name, r.text) for r in rows]
    finally:
        db.close()

def log_usage(telegram_id, action_type):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if user:
            new_log = UsageLog(user_id=user.id, action_type=action_type)
            db.add(new_log)
            db.commit()
    finally:
        db.close()

def get_monthly_usage(telegram_id, action_type='post_publish'):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user: return 0
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        count = db.query(UsageLog).filter(
            UsageLog.user_id == user.id,
            UsageLog.action_type == action_type,
            UsageLog.createdAt >= thirty_days_ago
        ).count()
        return count
    finally:
        db.close()

def get_user_usage_info(telegram_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user:
            return {'tier': 'Free', 'used': 0, 'limit': 30}

        # Sync tier if expired
        tier = user.subscription_tier or 'free'
        if user.proExpiresAt and user.proExpiresAt < datetime.utcnow():
            user.subscription_tier = 'free'
            user.isPro = False
            db.commit()
            tier = 'free'

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        used = db.query(UsageLog).filter(
            UsageLog.user_id == user.id,
            UsageLog.action_type == 'post_publish',
            UsageLog.createdAt >= thirty_days_ago
        ).count()

        limits = {'free': 30, 'pro': 150, 'business': 450}
        limit = limits.get(tier, 30)

        return {
            'tier': tier.capitalize(),
            'used': used,
            'limit': limit
        }
    finally:
        db.close()
# --- USER CHANNELS HELPERS ---

def get_user_channels(telegram_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user: return []
        return db.query(UserChannel).filter(UserChannel.user_id == user.id).all()
    finally:
        db.close()

def add_user_channel(telegram_id, username):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user:
            user = User(telegramId=telegram_id)
            db.add(user)
            db.commit()
            db.refresh(user)
        
        username = username.strip().replace('@', '')
        if not db.query(UserChannel).filter(UserChannel.user_id == user.id, UserChannel.channel_username == username).first():
            db.add(UserChannel(user_id=user.id, channel_username=username, is_default=True))
            db.commit()
    finally:
        db.close()

def delete_user_channel(telegram_id, channel_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if user:
            db.query(UserChannel).filter(UserChannel.user_id == user.id, UserChannel.id == channel_id).delete()
            db.commit()
    finally:
        db.close()

def check_user_limit(telegram_id, action_type='post_publish'):
    """
    Проверяет месячные лимиты:
    Free: 30/mo, Pro: 150/mo, Business: 450/mo
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user: return True 

        # Считаем использование за последние 30 дней
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        usage = db.query(UsageLog).filter(
            UsageLog.user_id == user.id, 
            UsageLog.action_type == action_type,
            UsageLog.createdAt >= thirty_days_ago
        ).count()
        
        # Определяем лимит по тарифу
        tier = user.subscription_tier or 'free'
        # Если PRO истек, сбрасываем на free
        if user.proExpiresAt and user.proExpiresAt < datetime.utcnow():
            user.subscription_tier = 'free'
            user.isPro = False
            db.commit()
            tier = 'free'

        limits = {'free': 30, 'pro': 150, 'business': 450}
        limit = limits.get(tier, 30)

        return usage < limit
    finally:
        db.close()

def set_user_tier(telegram_id, tier, days=30):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if user:
            user.subscription_tier = tier
            user.isPro = (tier != 'free')
            user.proExpiresAt = datetime.utcnow() + timedelta(days=days)
            db.commit()
            return True
        return False
    finally:
        db.close()

# --- ADMIN HELPERS ---

def get_all_users(limit=50, offset=0):
    db = SessionLocal()
    try:
        return db.query(User).order_by(User.createdAt.desc()).limit(limit).offset(offset).all()
    finally:
        db.close()

def get_user_by_tg_id(tg_id):
    db = SessionLocal()
    try:
        return db.query(User).filter(User.telegramId == tg_id).first()
    finally:
        db.close()

def get_all_bots():
    db = SessionLocal()
    try:
        return db.query(BotInstance).all()
    finally:
        db.close()

def toggle_bot_status(bot_id):
    db = SessionLocal()
    try:
        bot = db.query(BotInstance).filter(BotInstance.id == bot_id).first()
        if bot:
            bot.is_active = not bot.is_active
            db.commit()
            return bot.is_active
        return None
    finally:
        db.close()

def get_global_stats():
    db = SessionLocal()
    try:
        users_count = db.query(User).count()
        bots_count = db.query(BotInstance).count()
        pro_count = db.query(User).filter(User.isPro == True).count()
        total_posts = db.query(Queue).filter(Queue.status == 'posted').count()
        return {
            'users': users_count,
            'bots': bots_count,
            'pro': pro_count,
            'posts': total_posts
        }
    finally:
        db.close()

def get_or_create_user(telegram_id, username=None):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user:
            user = User(telegramId=telegram_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()

def check_pro_status(telegram_id):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user: return False
        if not user.isPro: return False
        if user.proExpiresAt and user.proExpiresAt < datetime.utcnow():
            # Auto expire
            user.isPro = False
            db.commit()
            return False
        return True
    finally:
        db.close()

def create_manual_payment(telegram_id, amount, receipt_url=None):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegramId == telegram_id).first()
        if not user:
            user = User(telegramId=telegram_id)
            db.add(user)
            db.commit()
            db.refresh(user)
            
        new_payment = ManualPayment(userId=user.id, amount=amount, receiptUrl=receipt_url, status="PENDING")
        db.add(new_payment)
        db.commit()
        return new_payment.id
    finally:
        db.close()

def approve_payment(payment_id):
    db = SessionLocal()
    try:
        payment = db.query(ManualPayment).filter(ManualPayment.id == payment_id).first()
        if payment:
            payment.status = "APPROVED"
            user = db.query(User).filter(User.id == payment.userId).first()
            if user:
                user.isPro = True
                user.proExpiresAt = datetime.utcnow() + timedelta(days=30)
            db.commit()
            return True, user.telegramId if user else None
        return False, None
    finally:
        db.close()

from datetime import timedelta
init_db()
