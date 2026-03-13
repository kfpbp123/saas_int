from google import genai
from google.genai import types
import config
import re
import requests
from bs4 import BeautifulSoup
import time

# Переключаемся на самую продвинутую модель, она лучше понимает контекст игр
MODEL_ID = "gemini-2.0-flash"
client = genai.Client(api_key=config.GEMINI_KEY)

PROMPTS = {
    "uz": "Siz Minecraft olami haqidagi Telegram kanali muharririsiz. Qiziqarli post yozing.",
    "ru": "Вы профессиональный редактор Telegram-канала о Minecraft. Напишите интересный пост на основе данных. Используйте эмодзи и HTML-оформление.",
    "en": "You are a professional Minecraft community editor. Write an engaging post."
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
    
    # Пытаемся сделать промпт максимально безопасным для ИИ
    full_prompt = f"{selected_prompt}\n\nОПИСАНИЕ ИГРОВОГО КОНТЕНТА (MINECRAFT):\n{user_input}\n{site_content}\n\nНапиши обзорный пост для геймеров. Используй HTML <b> и <blockquote>."
    
    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
    ]

    for attempt in range(3):
        try:
            # На второй попытке упрощаем запрос до минимума
            current_prompt = full_prompt if attempt == 0 else f"Напиши короткий пост про этот мод Minecraft (используй {persona}): {user_input[:200]}"
            
            response = client.models.generate_content(
                model=MODEL_ID, 
                contents=current_prompt,
                config=types.GenerateContentConfig(safety_settings=safety_settings)
            )
            
            if response.text:
                final_text = response.text.strip()
                final_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', final_text)
                return final_text
            
            print(f"⚠️ Попытка {attempt+1}: Модель вернула пустой ответ (возможно, блок).")
            time.sleep(1)
        except Exception as e:
            print(f"❌ Ошибка API на попытке {attempt+1}: {str(e)}")
            time.sleep(1)
            
    return "⚠️ ИИ отказался обрабатывать этот текст из-за фильтров (слишком много слов о взрывах/оружии). Попробуйте отправить ссылку на мод или сократить описание."

def rewrite_post(text, style="short"):
    instruction = f"Перепиши этот текст в стиле: {style}. Сохрани HTML."
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=f"{instruction}\n\nТекст:\n{text}")
        return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', response.text.strip())
    except: return text

def chat_with_ai(user_message):
    try:
        response = client.models.generate_content(model=MODEL_ID, contents=f"Ты помощник в канале Minecraft. Отвечай кратко.\nПользователь: {user_message}")
        return response.text.strip()
    except: return "Ошибка чата."
