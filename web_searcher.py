import requests
from bs4 import BeautifulSoup
import re
import config

def get_trending_youtube():
    """Ищет популярные видео о модах Bedrock/MCPE на YouTube"""
    try:
        # Ищем именно Bedrock и Addons
        query = "Minecraft+Bedrock+Addons+2026+top+MCPE"
        url = f"https://www.youtube.com/results?search_query={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", response.text)
        unique_ids = list(dict.fromkeys(video_ids))[:6]
        
        results = []
        for vid in unique_ids:
            results.append({
                "title": f"Bedrock/MCPE Update {vid}",
                "url": f"https://www.youtube.com/watch?v={vid}",
                "source": "YouTube",
                "version": "Bedrock/PE"
            })
        return results
    except Exception as e:
        print(f"❌ YouTube search error: {e}")
        return []

def get_curseforge_mods():
    """Парсит популярные дополнения с CurseForge (MCPE/Bedrock)"""
    try:
        # Раздел Customization или Addons для Bedrock
        url = "https://www.curseforge.com/minecraft-bedrock/addons"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        mods = []
        # Ищем ссылки на проекты
        links = soup.find_all("a", href=re.compile(r"/minecraft-bedrock/addons/"))
        
        seen = set()
        for link in links:
            href = link.get('href')
            if href not in seen and len(mods) < 6:
                seen.add(href)
                name = link.get_text(strip=True)
                if not name or len(name) < 3: continue
                
                mods.append({
                    "title": name,
                    "url": "https://www.curseforge.com" + href,
                    "source": "CurseForge",
                    "version": "Bedrock/PE"
                })
        return mods
    except Exception as e:
        print(f"❌ CurseForge error: {e}")
        return []

def get_all_trends():
    yt = get_trending_youtube()
    cf = get_curseforge_mods()
    return yt + cf
