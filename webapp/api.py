from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import database
import config
import core
import utils
import comments_analyzer
import web_searcher
import ai_generator
import uvicorn
import os
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Mine Bot TMA API")

class ChatRequest(BaseModel):
    message: str
    user_id: int = 0
    lang: str = 'uz'

# Разрешаем CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

class PostUpdate(BaseModel):
    text: Optional[str] = None
    scheduled_time: Optional[int] = None

@app.get("/api/stats")
async def get_stats():
    return database.get_stats()

@app.get("/api/queue")
async def get_queue():
    print(f"📁 API accessing DB at: {database.DB_PATH}")
    posts = database.get_all_pending()
    print(f"📊 API: Found {len(posts)} pending posts. Full list: {[p[0] for p in posts]}")
    result = []
    for p in posts:
        result.append({
            "id": p[0],
            "photo_id": p[1],
            "text": p[2],
            "document_id": p[3],
            "channel": p[4] or config.DEFAULT_CHANNEL,
            "scheduled_time": p[5]
        })
    return result

@app.delete("/api/queue/{post_id}")
async def delete_post(post_id: int):
    database.delete_from_queue(post_id)
    return {"status": "ok"}

@app.put("/api/queue/{post_id}")
async def update_post(post_id: int, data: PostUpdate):
    if data.text is not None:
        database.update_post_text(post_id, data.text)
    if data.scheduled_time is not None:
        database.update_post_time(post_id, data.scheduled_time)
    return {"status": "ok"}

@app.post("/api/queue/{post_id}/publish")
async def publish_now(post_id: int):
    posts = database.get_all_pending()
    post = next((p for p in posts if p[0] == post_id), None)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    success = core.publish_post_data(post[0], post[1], post[2], post[3], post[4] or config.DEFAULT_CHANNEL)
    if success:
        return {"status": "ok"}
    raise HTTPException(status_code=500, detail="Publish failed")

@app.get("/api/channels")
async def get_channels_list(user_id: int = 0):
    channels = utils.get_channels()
    active = utils.get_active_channel(user_id or getattr(config, 'ADMIN_IDS', [0])[0])
    return {"channels": channels, "active": active}

@app.post("/api/channels/set")
async def set_active_channel(channel: str, user_id: int = 0):
    uid = user_id or getattr(config, 'ADMIN_IDS', [0])[0]
    database.set_user_setting(uid, channel=channel)
    return {"status": "ok"}

@app.get("/api/ai/analyze")
async def get_ai_analysis():
    report = comments_analyzer.analyze_comments()
    return {"report": report}

@app.get("/api/trends")
async def get_web_trends():
    trends = web_searcher.get_all_trends()
    return {"trends": trends}

@app.post("/api/ai/chat")
async def ai_chat_handler(req: ChatRequest):
    stats = database.get_stats()
    channel = utils.get_active_channel(req.user_id)
    comments = database.get_all_comments()[-20:]
    comm_text = "\n".join([f"- {c[0]}: {c[1]}" for c in comments])
    
    context = f"""
    [SYSTEM CONTEXT]
    You are an AI assistant for the Minecraft Telegram channel admin.
    Current Channel: {channel}
    Total Posts: {stats['total']}
    Pending in Queue: {stats['queue']}
    Focus: Minecraft Bedrock Edition (PE), Addons, Mobile.
    Recent User Comments:
    {comm_text or "No recent comments"}
    
    User Question: {req.message}
    """
    
    response = ai_generator.chat_with_ai(context, req.lang)
    return {"response": response}

def run_api():
    port = int(os.getenv("PORT", 8000))
    print(f"📡 Starting Web API on port {port}...")
    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        print(f"❌ Uvicorn failed: {e}")
