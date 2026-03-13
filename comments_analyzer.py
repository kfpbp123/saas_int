import google.generativeai as genai
import config
import database

genai.configure(api_key=config.GEMINI_KEY)
MODEL_ID = "gemini-1.5-flash"
model = genai.GenerativeModel(MODEL_ID)

def analyze_comments():
    comments = database.get_all_comments()
    if not comments:
        return "📭 Пока нет новых комментариев для анализа."
    
    comments_text = "\n".join([f"- {c[0]}: {c[1]}" for c in comments])
    prompt = f"""
    Проанализируй эти сообщения участников Minecraft-канала. 
    Какие моды, версии или карты они обсуждают? Что их интересует?
    Дай краткий отчет и идеи для следующих постов.
    
    Сообщения:
    {comments_text}
    """

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error in analyzer: {e}")
        return "⚠️ Ошибка при анализе комментариев."
