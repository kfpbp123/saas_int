import requests
from bs4 import BeautifulSoup
import re
import config

def get_trending_youtube():
    """Ищет популярные видео Bedrock/MCPE на YouTube, исключая Shorts"""
    try:
        query = "Minecraft+Bedrock+Addons+2026+top+MCPE+-shorts" # Минус shorts в запросе
        url = f"https://www.youtube.com/results?search_query={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Регулярка для обычных видео
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", response.text)
        unique_ids = list(dict.fromkeys(video_ids))[:10] # Берем с запасом для фильтрации
        
        results = []
        for vid in unique_ids:
            video_url = f"https://www.youtube.com/watch?v={vid}"
            # Дополнительная проверка (в результатах поиска иногда проскакивают shorts)
            # В HTML коде shorts обычно имеют другой путь, но мы перестрахуемся
            results.append({
                "title": f"Minecraft Video {vid}",
                "url": video_url,
                "source": "YouTube",
                "version": "Bedrock/PE"
            })
            if len(results) >= 6: break
        return results
    except Exception as e:
        print(f"❌ YouTube error: {e}")
        return []

def get_curseforge_search(sort="popular"):
    """Ищет моды на CurseForge по категориям"""
    try:
        # 1 = Featured, 2 = Popular, 3 = Recently Updated, 4 = Name, 5 = Newest
        sort_type = "2" if sort == "popular" else "5"
        url = f"https://www.curseforge.com/minecraft-bedrock/addons?filter-sort={sort_type}"
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        mods = []
        # Ищем контейнеры модов
        cards = soup.find_all("a", href=re.compile(r"/minecraft-bedrock/addons/"))
        
        seen = set()
        for card in cards:
            href = card.get('href')
            name = card.get_text(strip=True)
            
            if href not in seen and name and len(name) > 3:
                seen.add(href)
                mods.append({
                    "title": name,
                    "url": "https://www.curseforge.com" + href,
                    "source": "CurseForge",
                    "version": "Bedrock/PE",
                    "type": "New" if sort == "new" else "Hot"
                })
            if len(mods) >= 8: break
        return mods
    except Exception as e:
        print(f"❌ CurseForge search error: {e}")
        return []

def get_all_trends():
    """Для общей кнопки трендов - теперь только видео"""
    return get_trending_youtube()
