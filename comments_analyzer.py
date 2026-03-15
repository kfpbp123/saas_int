import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from groq import Groq
import config
import database
import re

# Настройка Gemini
genai.configure(api_key=config.GEMINI_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# Настройка Groq
groq_client = Groq(api_key=config.GROQ_API_KEY)
GROQ_MODEL_ID = "llama-3.3-70b-versatile"

def analyze_comments():
    try:
        comments = database.get_all_comments()
        if not comments:
            return "📭 Пока нет новых комментариев для анализа."
        
        # Берем последние 100 комментариев для анализа
        comments_text = "\n".join([f"- {c[0]}: {c[1]}" for c in comments[-100:]])
        
        prompt = f"""
        Ты — аналитик Minecraft-сообщества. Твоя задача — изучить комментарии пользователей и составить четкий, красивый отчет.
        
        Список комментариев:
        {comments_text}
        
        Используй следующий формат (строго):
        
        📊 <b>АНАЛИЗ СООБЩЕСТВА</b>
        
        ❓ <b>ЧТО СПРАШИВАЮТ:</b>
        • [Пункт 1 с эмодзи]
        • [Пункт 2 с эмодзи]
        
        💡 <b>ИДЕИ ДЛЯ ПОСТОВ:</b>
        • [Идея 1 с эмодзи]
        • [Идея 2 с эмодзи]
        
        🌈 <b>НАСТРОЙ:</b>
        [Краткое описание настроения аудитории]
        
        Пиши грамотно, понятно и вдохновляюще. Используй HTML теги (<b>, <i>).
        """

        # Режим Groq
        if config.AI_PROVIDER == "groq":
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return completion.choices[0].message.content.strip()

        # Режим Gemini (по умолчанию)
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        response = gemini_model.generate_content(prompt, safety_settings=safety_settings)
        return response.text.strip()
    except Exception as e:
        return f"❌ AI error ({config.AI_PROVIDER}): {e}"
