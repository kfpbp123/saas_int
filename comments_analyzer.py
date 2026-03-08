from google import genai
import config
import database

client = genai.Client(api_key=config.GEMINI_KEY)
MODEL_ID = "gemini-2.5-flash"

def analyze_comments():
    """Собирает комментарии из БД и просит Gemini сделать выжимку"""
    comments = database.get_all_comments()
    
    if not comments:
        return "📭 Пока нет новых комментариев от подписчиков."

    # Собираем все комментарии в один текст
    comments_text = "\n".join([f"- {c[0]}: {c[1]}" for c in comments])

    # Инструкция для ИИ
    prompt = f"""
    Ты — аналитик Telegram-канала о модах Minecraft.
    Ниже приведены комментарии пользователей из чата канала.
    Твоя задача — проанализировать их и составить краткую и понятную выжимку.
    
    Сгруппируй одинаковые запросы. Укажи количество людей, просящих одно и то же.
    Игнорируй спам, бессмысленные сообщения и обычное общение (типа "привет", "как дела", "круто").

    Формат ответа (используй эмодзи):
    💡 Запросы на моды/карты/шейдеры:
    - [Название или суть] (просили X человек)
    
    ⚠️ Проблемы и жалобы (если есть):
    - ...
    
    💬 Интересные идеи:
    - ...

    Комментарии для анализа:
    {comments_text}
    """

    try:
        response = client.models.generate_content(model=MODEL_ID, contents=prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Ошибка ИИ при анализе: {e}")
        return "❌ Произошла ошибка при анализе комментариев ИИ."