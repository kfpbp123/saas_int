from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
import config
from strings import BUTTONS

def get_main_menu(lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Кнопка Mini App - теперь центральный элемент управления
    if config.WEBAPP_URL and config.WEBAPP_URL.startswith('https'):
        try:
            markup.add(KeyboardButton("🚀 OPEN STUDIO", web_app=WebAppInfo(url=config.WEBAPP_URL)))
        except: pass
            
    markup.add(KeyboardButton(b['create']), KeyboardButton(b['lang']))
    markup.add(KeyboardButton(b['settings']), KeyboardButton(b['channels']))
    markup.add(KeyboardButton(b['analyze']), KeyboardButton(b['stats']))
    return markup

def get_user_channels_markup(channels, lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        markup.add(InlineKeyboardButton(f"❌ @{ch.channel_username}", callback_data=f"del_ch_{ch.id}"))
    markup.add(InlineKeyboardButton("➕ Add New Channel", callback_data="add_new_channel"))
    return markup

def get_settings_menu(lang='uz', auto_post=False):
    markup = InlineKeyboardMarkup(row_width=2)
    # Кнопка Mini App в инлайн-меню настроек (только если HTTPS)
    if config.WEBAPP_URL and config.WEBAPP_URL.startswith('https'):
        try:
            markup.add(InlineKeyboardButton("📱 Open Mini App", web_app=WebAppInfo(url=config.WEBAPP_URL)))
        except: pass
    
    auto_status = "🟢 ON" if auto_post else "🔴 OFF"
    markup.add(InlineKeyboardButton(f"🤖 Auto-Post: {auto_status}", callback_data="toggle_auto_post"))

    markup.add(
        InlineKeyboardButton("📢 Ad Text", callback_data="set_ad_text"),
        InlineKeyboardButton("💾 Backup DB", callback_data="db_backup")
    )
    markup.add(InlineKeyboardButton("📥 Export CSV", callback_data="csv_export"))
    return markup

def get_channels_markup(channels, active_channel):
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        status = "✅ " if ch == active_channel else ""
        markup.add(InlineKeyboardButton(f"{status}{ch}", callback_data=f"set_channel_{ch}"))
    markup.add(InlineKeyboardButton("➕ Add New", callback_data="add_new_channel"))
    return markup

def get_language_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="set_lang_uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang_ru"),
        InlineKeyboardButton("🇺🇸 English", callback_data="set_lang_en")
    )
    return markup

def get_cancel_markup(lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(KeyboardButton(b['cancel']))
    return markup

def get_draft_markup(lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(b['smart_q'], callback_data="add_to_smart_q"))
    markup.add(
        InlineKeyboardButton(b['now'], callback_data="pub_now"),
        InlineKeyboardButton(b['time'], callback_data="pub_queue_menu")
    )
    markup.add(
        InlineKeyboardButton(b['text'], callback_data="edit_text"),
        InlineKeyboardButton(b['rewrite'], callback_data="rewrite_menu")
    )
    markup.add(
        InlineKeyboardButton(b['add_ad'], callback_data="add_ad"),
        InlineKeyboardButton(b['delete'], callback_data="cancel_action")
    )
    return markup

def get_rewrite_menu(lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🧱 Short", callback_data="rw_short"),
        InlineKeyboardButton("🎮 Fun", callback_data="rw_fun")
    )
    markup.add(
        InlineKeyboardButton("👔 Pro", callback_data="rw_pro"),
        InlineKeyboardButton(b['back'], callback_data="back_to_draft")
    )
    return markup

def get_publish_queue_menu(target_id, prefix="sc", lang='uz'):
    """
    prefix: 'sc' для черновика (sched), 'qt' для очереди (qtime)
    """
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("+2h", callback_data=f"{prefix}_int_2_{target_id}"),       
        InlineKeyboardButton("+4h", callback_data=f"{prefix}_int_4_{target_id}"),       
        InlineKeyboardButton("+6h", callback_data=f"{prefix}_int_6_{target_id}")
    )
    markup.add(
        InlineKeyboardButton("+12h", callback_data=f"{prefix}_int_12_{target_id}"),   
        InlineKeyboardButton("+24h", callback_data=f"{prefix}_int_24_{target_id}"),
        InlineKeyboardButton("🕒 Custom", callback_data=f"{prefix}_ex_{target_id}")
    )
    markup.add(InlineKeyboardButton(b['back'], callback_data="back_to_draft" if prefix == "sc" else "q_page_0"))
    return markup

def get_queue_manage_markup(post_id, page, lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = InlineKeyboardMarkup(row_width=2)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"q_page_{page-1}"))
    nav_row.append(InlineKeyboardButton("➡️", callback_data=f"q_page_{page+1}"))
    markup.add(*nav_row)
    markup.add(
        InlineKeyboardButton(b['text'], callback_data=f"q_edit_{post_id}"),
        InlineKeyboardButton(b['time'], callback_data=f"q_time_{post_id}")
    )
    markup.add(
        InlineKeyboardButton(b['publish'], callback_data=f"q_pub_{post_id}"),
        InlineKeyboardButton(b['delete'], callback_data=f"q_del_{post_id}")
    )
    return markup

def get_pro_upgrade_markup(lang='uz'):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("💎 Buy PRO ($9.99/mo)", callback_data="buy_pro"))
    return markup

# --- ADMIN PANEL MARKUPS ---

def get_admin_main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("👤 Users", callback_data="adm_users_0"),
        InlineKeyboardButton("🤖 Bot Instances", callback_data="adm_bots")
    )
    markup.add(
        InlineKeyboardButton("🔎 Scanner Whitelist", callback_data="adm_scanner"),
        InlineKeyboardButton("📈 Global Stats", callback_data="adm_stats")
    )
    return markup

def get_admin_users_menu(users, page=0):
    markup = InlineKeyboardMarkup(row_width=1)
    for u in users:
        tier = u.subscription_tier or "Free"
        status = "💎" if u.isPro else "👤"
        markup.add(InlineKeyboardButton(f"{status} {u.username or u.telegramId} | {tier}", callback_data=f"adm_user_view_{u.telegramId}"))
    
    # Навигация
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"adm_users_{page-1}"))
    nav.append(InlineKeyboardButton("➡️ Next", callback_data=f"adm_users_{page+1}"))
    markup.add(*nav)
    markup.add(InlineKeyboardButton("🔎 Search by ID", callback_data="adm_user_search"))
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_main"))
    return markup

def get_admin_user_manage_markup(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Free", callback_data=f"adm_set_tier_free_{user_id}"),
        InlineKeyboardButton("Pro", callback_data=f"adm_set_tier_pro_{user_id}"),
        InlineKeyboardButton("Business", callback_data=f"adm_set_tier_business_{user_id}")
    )
    markup.add(InlineKeyboardButton("🔙 Back to Users", callback_data="adm_users_0"))
    return markup

def get_admin_bots_menu(bots):
    markup = InlineKeyboardMarkup(row_width=1)
    for b in bots:
        status = "🟢" if b.is_active else "🔴"
        markup.add(InlineKeyboardButton(f"{status} {b.bot_username or b.id} | {b.id}", callback_data=f"adm_bot_toggle_{b.id}"))
    markup.add(InlineKeyboardButton("➕ Add New Token", callback_data="adm_bot_add"))
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_main"))
    return markup

def get_admin_scanner_menu(channels):
    markup = InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        markup.add(InlineKeyboardButton(f"❌ @{ch}", callback_data=f"adm_scan_del_{ch}"))
    markup.add(InlineKeyboardButton("➕ Add New Whitelist Channel", callback_data="adm_scan_add"))
    markup.add(InlineKeyboardButton("🔙 Back to Admin", callback_data="adm_main"))
    return markup
