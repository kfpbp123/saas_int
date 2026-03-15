import requests
from bs4 import BeautifulSoup
import re
import config

def get_trending_youtube():
    """Ищет популярные видео Bedrock/MCPE на YouTube, исключая Shorts"""
    try:
        query = "Minecraft+Bedrock+Addons+2026+top+MCPE+-shorts"
        url = f"https://www.youtube.com/results?search_query={query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", response.text)
        unique_ids = list(dict.fromkeys(video_ids))[:10]
        
        results = []
        for vid in unique_ids:
            results.append({
                "title": f"Bedrock Video {vid}",
                "url": f"https://www.youtube.com/watch?v={vid}",
                "source": "YouTube",
                "version": "Bedrock/PE"
            })
            if len(results) >= 6: break
        return results
    except Exception as e:
        print(f"❌ YouTube error: {e}")
        return []

def get_curseforge_search(sort="popular"):
    """Парсит моды с CurseForge (Bedrock Addons)"""
    try:
        # Типы сортировки: 2 = Popular, 5 = Newest
        sort_type = "2" if sort == "popular" else "5"
        # Используем поиск, так как он более стабилен в выдаче HTML
        url = f"https://www.curseforge.com/minecraft-bedrock/search?class=addons&sortType={sort_type}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.curseforge.com/"
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ CurseForge returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        mods = []
        
        # Ищем карточки проектов. CurseForge часто меняет классы, 
        # поэтому ищем ссылки, содержащие путь к аддонам.
        links = soup.find_all("a", href=re.compile(r"/minecraft-bedrock/addons/"))
        
        seen = set()
        for link in links:
            href = link.get('href')
            # Находим имя (обычно это текст внутри ссылки или в дочернем span)
            name = link.get_text(strip=True)
            
            # Фильтруем мусор и дубликаты
            if href and name and len(name) > 3 and "/minecraft-bedrock/addons/" in href:
                # Если ссылка относительная, добавляем домен
                full_url = href if href.startswith("http") else "https://www.curseforge.com" + href
                
                # Избегаем дублей по URL
                if full_url not in seen:
                    seen.add(full_url)
                    mods.append({
                        "title": name,
                        "url": full_url,
                        "source": "CurseForge",
                        "version": "Bedrock",
                        "type": "New" if sort == "new" else "Hot"
                    })
            
            if len(mods) >= 10: break
            
        return mods
    except Exception as e:
        print(f"❌ CurseForge search error: {e}")
        return []

def get_all_trends():
    return get_trending_youtube()
