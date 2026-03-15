import requests
from bs4 import BeautifulSoup
import re
import config

def get_trending_youtube():
    """Ищет популярные видео Bedrock/MCPE на YouTube, исключая Shorts"""
    try:
        query = "Minecraft+Bedrock+Addons+2026+top+MCPE+-shorts"
        url = f"https://www.youtube.com/results?search_query={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", response.text)
        unique_ids = list(dict.fromkeys(video_ids))[:10]
        results = []
        for vid in unique_ids:
            results.append({"title": f"Bedrock Video {vid}", "url": f"https://www.youtube.com/watch?v={vid}", "source": "YouTube", "version": "Bedrock/PE"})
            if len(results) >= 6: break
        return results
    except: return []

def get_mcpedl_mods():
    """Парсит свежие моды с MCPEDL (Самый надежный источник для Bedrock)"""
    try:
        url = "https://mcpedl.com/category/mods/"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        mods = []
        # Ищем заголовки статей (модов)
        posts = soup.find_all("h2", class_="entry-title")
        for post in posts:
            link = post.find("a")
            if link:
                name = link.get_text(strip=True)
                href = link.get('href')
                if name and href:
                    mods.append({
                        "title": name,
                        "url": href,
                        "source": "MCPEDL",
                        "version": "Bedrock",
                        "type": "Hot"
                    })
            if len(mods) >= 6: break
        return mods
    except Exception as e:
        print(f"❌ MCPEDL error: {e}")
        return []

def get_curseforge_search(sort="popular"):
    """Парсит моды с CurseForge (с фолбеком на MCPEDL)"""
    mods = []
    try:
        sort_type = "2" if sort == "popular" else "5"
        url = f"https://www.curseforge.com/minecraft-bedrock/addons?filter-sort={sort_type}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Ищем ссылки внутри элементов, которые могут быть карточками
            links = soup.find_all("a", href=re.compile(r"/minecraft-bedrock/addons/"))
            seen = set()
            for link in links:
                name = link.get_text(strip=True)
                href = link.get('href')
                if name and len(name) > 5 and href not in seen:
                    seen.add(href)
                    mods.append({
                        "title": name,
                        "url": "https://www.curseforge.com" + href if not href.startswith("http") else href,
                        "source": "CurseForge",
                        "version": "Bedrock",
                        "type": "New" if sort == "new" else "Hot"
                    })
                if len(mods) >= 6: break
    except: pass

    # Если CurseForge ничего не отдал (заблокировал), берем с MCPEDL
    if not mods:
        print("⚠️ CurseForge blocked or empty, switching to MCPEDL...")
        mods = get_mcpedl_mods()
        
    return mods

def get_all_trends():
    return get_trending_youtube()
