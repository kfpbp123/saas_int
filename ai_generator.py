from google import genai
from google.genai import types
import config
import re
import requests
from bs4 import BeautifulSoup
import time

# Используем стабильную модель
MODEL_ID = "gemini-1.5-flash"
client = genai.Client(api_key=config.GEMINI_KEY)

PROMPTS = {
    "uz": "Siz Minecraft modlari haqidagi Telegram kanali uchun kreativ muharrirsiz. Faqat o'zbek tilida (lotin alifbosida) javob bering.",
    "ru": "Вы профессиональный редактор Telegram-канала о Minecraft. Пишите только на русском языке. Используйте геймерский сленг, но оставайтесь понятным.",
    "en": "You are a creative editor for a Minecraft community Telegram channel. Write only in English."
}

TEMPLATES = {
    "standard": """
📦 <b>[Название]</b>

<blockquote expandable><b>Что это? / Bu nima?</b>
[Описание]

<b>Фишки / Xususiyatlar:</b>
• [Фишка 1]
• [Фишка 2]

🎮 Версия / Versiya: [Версия]</blockquote>

<blockquote>💖 - Лайк
💔 - Не очень</blockquote>

#Minecraft #[Категория]""",

    "list": """
🔥 <b>[Название]: ТОП ФИШЕК</b>

<blockquote expandable>
1️⃣ [Фишка 1]
2️⃣ [Фишка 2]
3️⃣ [Фишка 3]
4️⃣ [Фишка 4]

🎮 Версия / Versiya: [Версия]
</blockquote>

#Minecraft #[Категория]""",

    "review": """
🧐 <b>ОБЗОР: [Название]</b>

<blockquote expandable>
[Краткое мнение о контенте]

✅ <b>Плюсы:</b>
- [Плюс 1]
- [Плюс 2]

❌ <b>Минусы:</b>
- [Минус 1]

🎮 Версия / Versiya: [Версия]
</blockquote>

#Minecraft #[Категория]"""
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

def generate_post(user_input, persona="uz", template="standard"):
    url = extract_url(user_input)
    site_content = fetch_page_content(url) if url else ""
    
    selected_prompt = PROMPTS.get(persona, PROMPTS["uz"])
    selected_template = TEMPLATES.get(template, TEMPLATES["standard"])
    
    full_prompt = f"{selected_prompt}\n\nНАПИШИ ПОСТ СТРОГО ПО ЭТОМУ ШАБЛОНУ:\n{selected_template}\n\nДАННЫЕ:\n{user_input}\n{site_content}"
    
    # Настройки безопасности: отключаем блокировку потенциально "опасного" контента, 
    # который часто срабатывает ложно на словах про животных или моды.
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]

    for attempt in range(3): # Увеличим до 3 попыток
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
            
            # Если текст пустой, возможно, сработал внутренний фильтр, пробуем упрощенный запрос
            if attempt == 1:
                full_prompt = f"Напиши пост про этот мод для Minecraft: {user_input}. Используй русский язык."
                
            time.sleep(1.5)
        except Exception as e:
            print(f"Попытка {attempt+1} провалена: {e}")
            time.sleep(1.5)
            
    return "⚠️ Нейросеть отклонила запрос по соображениям безопасности или из-за сбоя. Попробуйте изменить описание (убрать слова 'альфа', 'стать животным' и т.д.) или просто отправьте ссылку на мод."

def rewrite_post(text, style="short"):
    styles = {
        "short": "Сделай текст коротким и лаконичным.",
        "fun": "Сделай текст веселым и драйвовым.",
        "pro": "Сделай текст профессиональным и детальным.",
        "scientist": "Перепиши как безумный ученый.",
        "boring": "Сделай текст максимально скучным."
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
