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
    "uz": "Siz Minecraft olami haqidagi Telegram kanali muharririsiz. Berilgan ma'lumotlar asosida qiziqarli va chiroyli post yozing. Faqat o'zbek tilida (lotin alifbosida) javob bering.",
    "ru": "Вы профессиональный редактор Telegram-канала о Minecraft. Напишите интересный, вовлекающий пост на основе предоставленных данных. Используйте подходящие эмодзи и HTML-оформление (жирный текст, цитаты).",
    "en": "You are a professional Minecraft community editor. Write an engaging post based on the provided data. Use emojis and HTML formatting."
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
    site_content = fetch_page_content(url) if url else ""
    
    selected_prompt = PROMPTS.get(persona, PROMPTS["uz"])
    
    # Свободный промпт без шаблонов
    full_prompt = f"{selected_prompt}\n\nДАННЫЕ ДЛЯ ПОСТА:\n{user_input}\n{site_content}\n\nНапиши качественный пост, используя HTML-теги <b> и <blockquote>."
    
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]

    for attempt in range(2):
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
            time.sleep(1)
        except:
            time.sleep(1)
            
    return "⚠️ Не удалось сгенерировать пост. Попробуйте еще раз."

def rewrite_post(text, style="short"):
    styles = {
        "short": "Сделай текст коротким и лаконичным.",
        "fun": "Сделай текст веселым и драйвовым.",
        "pro": "Сделай текст профессиональным и детальным.",
        "scientist": "Перепиши как ученый.",
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
