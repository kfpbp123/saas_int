from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import config
from strings import BUTTONS

def get_main_menu(lang='uz'):
    b = BUTTONS.get(lang, BUTTONS['uz'])
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton(b['create']), KeyboardButton(b['ai_chat']))
    markup.add(KeyboardButton(b['queue']), KeyboardButton(b['lang']))
    markup.add(KeyboardButton(b['channels']), KeyboardButton(b['stats']))
    markup.add(KeyboardButton(b['settings']), KeyboardButton(b['analyze']))
    return markup

def get_settings_menu(lang='uz'):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📢 Ad Text", callback_data="set_ad_text"),
        InlineKeyboardButton("➕ Add Channel", callback_data="add_new_channel")
    )
    markup.add(InlineKeyboardButton("💾 Backup DB", callback_data="db_backup"))
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
