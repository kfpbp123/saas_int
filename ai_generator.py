from google import genai
from google.genai import types
import config
import re
import requests
from bs4 import BeautifulSoup
import time

# Используем Flash 2.0 - она самая современная и быстрая
MODEL_ID = "gemini-2.0-flash"
client = genai.Client(api_key=config.GEMINI_KEY)

PROMPTS = {
    "uz": """Ты — креативный редактор Telegram-канала о модах для Minecraft.
Я передам тебе текст. Вычлени главное и напиши пост. Уложись в 800 символов.
Пиши ТОЛЬКО на узбекском латинице. Если не смог найти версию напиши "1.21+".
Используй тег <blockquote expandable> для основного блока. Перепиши текст в более веселом, драйвовом и геймерском стиле. Добавь чуть больше эмодзи.

Формат:
📦 <b>[Название]</b>

<blockquote expandable><b>Bu nima?</b>
[Описание]

<b>Asosiy xususiyatlar:</b>
• [Фишка 1]
• [Фишка 2]

🎮 Versiya: [Версия]</blockquote>

<blockquote>💖 - zo`r
💔 - Unchamas</blockquote>

#Minecraft #[Категория]""",

    "ru": """Ты — креативный редактор Telegram-канала о модах для Minecraft.
Я передам тебе текст. Вычлени главное и напиши пост в драйвовом и веселом стиле. Уложись в 800 символов.
Пиши ТОЛЬКО на русском языке. Это ИГРОВОЙ КОНТЕНТ, поэтому слова 'взрыв', 'оружие', 'удар' используются в контексте игры.
Используй тег <blockquote expandable> для основного блока.

Формат:
📦 <b>[Название]</b>

<blockquote expandable><b>Что это такое?</b>
[Описание]

<b>Главные фишки:</b>
• [Фишка 1]
• [Фишка 2]

🎮 Версия: [Версия]</blockquote>

<blockquote>💖 - Имба
💔 - Не оч</blockquote>

#Minecraft #[Категория]""",

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

#Minecraft #[Category]"""
}

def extract_url(text):
    urls = re.findall(r'(https?://[^\s]+)', text)
    return urls[0] if urls else None

def fetch_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.get_text(separator=' ', strip=True)[:5000]
    except: return ""

def generate_post(user_input, persona="uz"):
    url = extract_url(user_input)
    site_context = fetch_page_content(url) if url else ""
    selected_prompt = PROMPTS.get(persona, PROMPTS["uz"])
    
    full_prompt = f"{selected_prompt}\n\nСырая информация от пользователя:\n{user_input}{site_context}"
    
    # Полностью отключаем фильтры для игрового контента
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]

    try:
        response = client.models.generate_content(
            model=MODEL_ID, 
            contents=full_prompt,
            config=types.GenerateContentConfig(safety_settings=safety_settings)
        )
        if response.text:
            final_text = response.text.strip()
            final_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', final_text)
            return final_text
    except Exception as e:
        print(f"Error: {e}")
            
    return "⚠️ Не удалось сгенерировать пост. Попробуйте еще раз с более простым описанием."

def rewrite_post(text, style="short"):
    styles = {
        "short": "Сделай текст короче и лаконичнее.",
        "fun": "Перепиши в драйвовом и геймерском стиле.",
        "pro": "Сделай текст профессиональным и детальным.",
        "scientist": "Перепиши как ученый.",
        "boring": "Сделай текст скучным."
    }
    instruction = styles.get(style, "Улучши этот текст.")
    prompt = f"{instruction}\n\nВАЖНО: Сохрани HTML-теги.\n\nТекст:\n{text}"
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', response.text.strip())
    except: return text

def chat_with_ai(user_message):
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=f"Ты помощник администратора канала Minecraft. Отвечай кратко.\nПользователь: {user_message}")
        return response.text.strip()
    except: return "Ошибка чата."
