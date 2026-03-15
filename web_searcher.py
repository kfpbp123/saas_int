import requests
from bs4 import BeautifulSoup
import re
import config

def get_trending_youtube():
    """Ищет популярные видео о модах на YouTube"""
    try:
        query = "Minecraft+Mods+1.21+2026+top"
        url = f"https://www.youtube.com/results?search_query={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        
        # YouTube подгружает контент через JS, но в HTML есть первичные данные
        # Ищем паттерны ссылок на видео /watch?v=...
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", response.text)
        unique_ids = list(dict.fromkeys(video_ids))[:5]
        
        results = []
        for vid in unique_ids:
            results.append({
                "title": f"Popular Video {vid}", # В идеале парсить title, но для теста ссылок хватит
                "url": f"https://www.youtube.com/watch?v={vid}",
                "source": "YouTube"
            })
        return results
    except Exception as e:
        print(f"❌ YouTube search error: {e}")
        return []

def get_curseforge_mods(category="popular"):
    """Парсит популярные моды с CurseForge"""
    try:
        # Ссылка на моды для Fabric/Forge (под версию 1.21.1 например)
        # Категории: mc-mods?filter-sort=2 (Popular), 5 (Recent)
        sort_map = {"popular": "2", "recent": "5"}
        sort_val = sort_map.get(category, "2")
        url = f"https://www.curseforge.com/minecraft/search?class=mc-mods&sortType={sort_val}&pageSize=20"
        
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        mods = []
        # Находим карточки модов (селекторы могут меняться, подбираем актуальные)
        cards = soup.find_all("div", class_="results-card") or soup.find_all("a", href=re.compile(r"/minecraft/mc-mods/"))
        
        seen_urls = set()
        for card in cards:
            if len(mods) >= 5: break
            
            href = card.get('href') if card.name == 'a' else card.find('a').get('href')
            if not href.startswith("http"):
                href = "https://www.curseforge.com" + href
            
            if href in seen_urls: continue
            seen_urls.add(href)
            
            # Пытаемся вытащить имя из текста ссылки или соседних элементов
            name = card.get_text(strip=True).split('\n')[0][:50]
            mods.append({
                "title": name or "Unknown Mod",
                "url": href,
                "source": "CurseForge"
            })
            
        return mods
    except Exception as e:
        print(f"❌ CurseForge search error: {e}")
        return []

def get_all_trends():
    """Собирает все тренды вместе"""
    yt = get_trending_youtube()
    cf = get_curseforge_mods("popular")
    return yt + cf
