from google import genai
import config
import re
import requests
from bs4 import BeautifulSoup

client = genai.Client(api_key=config.GEMINI_KEY)
MODEL_ID = "gemini-2.5-flash"

PROMPTS = {
    "uz": """Ты — креативный редактор Telegram-канала о модах для Minecraft.
Я передам тебе текст. Вычлени главное и напиши пост. Уложись в 800 символов.
Пиши ТОЛЬКО на узбекском латинице. Если не смог найти версию напиши "1.21+".
Используй тег <blockquote expandable> для основного блока.

Формат:
📦 <b>[Название мода]</b>

<blockquote expandable><b>Bu nima?</b>
[Описание]

<b>Asosiy xususiyatlar:</b>
• [Фишка 1]
• [Фишка 2]

🎮 Versiya: [Версия]</blockquote>

<blockquote>💖 - zo`r
💔 - Unchamas</blockquote>

#[Хэштег1] #[Хэштег2]
""",

    "ru": """Ты — креативный редактор Telegram-канала о модах для Minecraft.
Я передам тебе текст. Вычлени главное и напиши пост в драйвовом и веселом стиле. Уложись в 800 символов.
Пиши ТОЛЬКО на русском языке.
Используй тег <blockquote expandable> для основного блока.

Формат:
📦 <b>[Название мода]</b>

<blockquote expandable><b>Что это такое?</b>
[Описание]

<b>Главные фишки:</b>
• [Фишка 1]
• [Фишка 2]

🎮 Версия: [Версия]</blockquote>

<blockquote>💖 - Имба
💔 - Не оч</blockquote>

#[Хэштег1] #[Хэштег2]
""",

    "en": """You are a creative editor for a Minecraft mods Telegram channel.
Extract the main points and write an engaging post. Keep it under 800 characters.
Write ONLY in English in an exciting tone.
Use the <blockquote expandable> tag for the main body.

Format:
📦 <b>[Mod Name]</b>

<blockquote expandable><b>What is it?</b>
[Description]

<b>Key Features:</b>
• [Feature 1]
• [Feature 2]

🎮 Version: [Version]</blockquote>

<blockquote>💖 - Awesome
💔 - Not great</blockquote>

#[Hashtag1] #[Hashtag2]
"""
}

def extract_url(text):
    urls = re.findall(r'(https?://[^\s]+)', text)
    return urls[0] if urls else None

def fetch_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        text = soup.get_text(separator=' ', strip=True)
        return text[:5000] 
    except Exception as e:
        print(f"⚠️ Не смог прочитать сайт {url}: {e}")
        return ""

def generate_post(user_input, persona="uz"):
    url = extract_url(user_input)
    site_context = ""
    
    if url:
        print(f"🔗 Найдена ссылка, читаю сайт: {url}")
        page_text = fetch_page_content(url)

    selected_prompt = PROMPTS.get(persona, PROMPTS["uz"])
    
    prompt = f"{selected_prompt}\n\nСырая информация от пользователя:\n{user_input}{site_context}"
    response = client.models.generate_content(model=MODEL_ID, contents=prompt)
    
    final_text = response.text.strip()
    
    # Конвертируем Markdown-звездочки в HTML-теги для жирного текста
    final_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', final_text)
    
    return final_text

def rewrite_post(text, style="short"):
    """Функция для переписывания готового черновика"""
    print(f"✨ Запрос на рерайт в стиле: {style}")
    
    styles = {
        "short": "Сделай текст короче и лаконичнее. Оставь только самую суть, убери лишнюю воду.",
        "fun": "Перепиши текст в более веселом, драйвовом и геймерском стиле. Добавь чуть больше эмодзи.",
        "pro": "Сделай текст более профессиональным, строгим и информативным."
    }
    
    prompt_instruction = styles.get(style, "Улучши этот текст.")
    
    # Формируем запрос
    prompt = f"{prompt_instruction}\n\nВАЖНО: Сохрани HTML-теги форматирования (<b>, <blockquote>) и все хэштеги в конце.\n\nОригинальный текст:\n{text}"
    
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        final_text = response.text.strip()
        
        # Исправляем возможные ошибки ИИ с Markdown
        final_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', final_text)
        return final_text
    except Exception as e:
        print(f"❌ Ошибка рерайта: {e}")
        return text # Если ошибка, возвращаем оригинал