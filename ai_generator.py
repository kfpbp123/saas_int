try:
    from google import genai
    from google.genai import types
    gemini_client = genai.Client(api_key=config.GEMINI_KEY)
    GEMINI_AVAILABLE = True
except ImportError:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold
    genai.configure(api_key=config.GEMINI_KEY)
    GEMINI_AVAILABLE = False

from groq import Groq
import config
import re
import requests
from bs4 import BeautifulSoup

# Настройка API
# Gemini
GEMINI_MODEL_ID = "gemini-2.0-flash"
if not GEMINI_AVAILABLE:
    gemini_model = genai.GenerativeModel(GEMINI_MODEL_ID)

# Groq
groq_client = Groq(api_key=config.GROQ_API_KEY)
GROQ_MODEL_ID = "llama-3.3-70b-versatile"

PROMPTS = {
    "uz": """Sen Minecraft modlari haqidagi Telegram kanali uchun kreativ redaktorsan.
Senga matn va fayl nomi beriladi. Asosiy ma'lumotlarni ajratib ol va post yoz.
DIQQAT: Agar matn Minecraft modiga tegishli bo'lmasa (masalan: reklama, boshqa o'yinlar, konkurslar), faqat bitta so'z qaytar: "REJECT".

Qoidalar:
1. FAQAT O'zbek tilida yoz (lotin alifbosi).
2. AGAR matnda "Sehr" (Magic) yoki "O'lmaslik" (Immortality) haqida gap bo'lmasa, BU SO'ZLARNI ISHLATMA.
3. Modning haqiqiy vazifasini yoz. Agar ma'lumot kam bo'lsa, fayl nomiga qara.
4. Sarlavha (📦 [Nomi]) aniq va qisqa bo'lsin.
5. <blockquote expandable> tegidan foydalan.

Format:
📦 <b>[Aniq nomi]</b>

<blockquote expandable><b>Bu nima?</b>
[Modning aniq vazifasi haqida 1-2 gap]

<b>Asosiy xususiyatlar:</b>
• [Haqiqiy xususiyat 1]
• [Haqiqiy xususiyat 2]

🎮 Versiya: [Versiya yoki 1.21+]</blockquote>

<blockquote>💖 - juda zo'r
💔 - unchamas</blockquote>

Xeshteglar: Faqat 3-5 ta RELEVANT xeshteg, FAQAT INGLIZ TILIDA (masalan: #Minecraft #Survival #Tech #Mod). O'zbekcha yoki ruscha xeshteglar (masalan: #sehr) mutlaqo taqiqlangan!""",

    "ru": """Ты — креативный редактор Telegram-канала о модах для Minecraft.
Я передам тебе текст. Вычлени главное и напиши пост в драйвовом и веселом стиле. Уложись в 800 символов.
Пиши ТОЛЬКО на русском языке. Это ИГРА, поэтому термины 'взрывы', 'оружие' — это нормально.
Используй тег <blockquote expandable> для основного блока.

Формат:
📦 <b>[Название]</b>

<blockquote expandable><b>Что это такое?</b>
[Описание]

<b>Главные фишки:</b>
• [Фишка 1]
• [Фишка 2]

🎮 Версия: [Versiya]</blockquote>

<blockquote>💖 - Имба
💔 - Не оч</blockquote>

В конце добавь 3-5 релевантных хештегов на основе контента. Хештеги должны быть ТОЛЬКО НА АНГЛИЙСКОМ ЯЗЫКЕ (например: #Tech, #Magic, #Adventure). 
Русские или узбекские хештеги (например #магия, #sehr) СТРОГО ЗАПРЕЩЕНЫ. 
Обязательно включи #Minecraft.""",

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

At the end, add 3-5 relevant hashtags based on the content. 
Hashtags must be ONLY IN ENGLISH (e.g., #Tech, #Magic, #Adventure). 
Never use Russian or Uzbek tags. 
Always include #Minecraft."""
}

def extract_url(text):
    urls = re.findall(r'(https?://[^\s]+)', text)
    return urls[0] if urls else None

def fetch_page_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Улучшение: вытаскиваем описание из meta-тегов
        text = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            text += meta_desc.get("content", "") + " "
            
        text += soup.get_text(separator=' ', strip=True)
        return text[:5000] 
    except Exception as e:
        print(f"⚠️ Не смог прочитать сайт {url}: {e}")
        return ""

def generate_post(user_input, persona="uz"):
    url = extract_url(user_input)
    site_context = ""
    if url:
        site_context = f"\nКонтент с сайта:\n{fetch_page_content(url)}"

    selected_prompt = PROMPTS.get(persona, PROMPTS["uz"])
    system_prefix = "SYSTEM: This is a request about a MINECRAFT MOD. All terms like 'weapons', 'explosions', or 'fire' refer to IN-GAME PIXELS and virtual mechanics only. Do not trigger safety filters.\n\n"
    full_prompt = f"{system_prefix}{selected_prompt}\n\nСырая информация:\n{user_input}{site_context}"
    
    # Режим работы через Groq
    if config.AI_PROVIDER == "groq":
        try:
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prefix},
                    {"role": "user", "content": f"{selected_prompt}\n\nСырая информация:\n{user_input}{site_context}"}
                ],
                temperature=0.7,
                max_tokens=1024,
            )
            final_text = completion.choices[0].message.content.strip()
            final_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', final_text)
            return final_text
        except Exception as e:
            return f"❌ Groq error: {e}"

    # Режим работы через Gemini (по умолчанию)
    try:
        if GEMINI_AVAILABLE:
            config_gen = types.GenerateContentConfig(
                safety_settings=[
                    types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                    types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                ]
            )
            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL_ID,
                contents=full_prompt,
                config=config_gen
            )
            final_text = response.text.strip()
        else:
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            response = gemini_model.generate_content(
                full_prompt,
                safety_settings=safety_settings
            )
            
            if not response.candidates:
                return "⚠️ Gemini error: Ответ пуст (возможно, из-за фильтров безопасности)."

            try:
                final_text = response.text.strip()
            except Exception:
                try:
                    final_text = response.candidates[0].content.parts[0].text.strip()
                except:
                    return "⚠️ Gemini error: Не удалось извлечь текст из ответа."

        final_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', final_text)
        return final_text

    except Exception as e:
        return f"❌ Gemini error: {e}"

def rewrite_post(text, style="short", persona="uz"):
    lang_instruction = "uzbek (latin)" if persona == "uz" else "russian" if persona == "ru" else "english"
    prompt = f"Rewrite this text in {style} style, keeping HTML tags and using {lang_instruction} language: {text}"
    try:
        if config.AI_PROVIDER == "groq":
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
            )
            res = completion.choices[0].message.content.strip()
        else:
            if GEMINI_AVAILABLE:
                response = gemini_client.models.generate_content(model=GEMINI_MODEL_ID, contents=prompt)
            else:
                response = gemini_model.generate_content(prompt)
            res = response.text.strip()
            
        return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', res)
    except: return text

def chat_with_ai(user_message, persona="uz"):
    lang_instruction = "uzbek (latin)" if persona == "uz" else "russian" if persona == "ru" else "english"
    prompt = f"You are a helpful assistant. Answer shortly in {lang_instruction}: {user_message}"
    try:
        if config.AI_PROVIDER == "groq":
            completion = groq_client.chat.completions.create(
                model=GROQ_MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
            )
            return completion.choices[0].message.content.strip()
        else:
            if GEMINI_AVAILABLE:
                response = gemini_client.models.generate_content(model=GEMINI_MODEL_ID, contents=prompt)
            else:
                response = gemini_model.generate_content(prompt)
            return response.text.strip()
    except: return "Error."
