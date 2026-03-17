from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import database
import config
import uvicorn
import threading

app = FastAPI(title="MineBot API")

# Разрешаем CORS, чтобы фронтенд с Vercel мог стучаться к нашему боту в Railway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # В продакшене заменим на URL твоего фронтенда
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SCHEMAS ---
class UserInfo(BaseModel):
    id: int
    telegramId: int
    username: Optional[str]
    isPro: bool
    tier: str
    used: int
    limit: int

class QueueItem(BaseModel):
    id: int
    text: Optional[str]
    photo_id: Optional[str]
    status: str
    scheduled_time: int
    channel: Optional[str]

# --- API ENDPOINTS ---

@app.get("/api/user/{tg_id}", response_model=UserInfo)
async def get_user(tg_id: int):
    user = database.get_user_by_tg_id(tg_id)
    if not user:
        # Если юзера нет, создаем (MVP подход)
        user = database.get_or_create_user(tg_id)
    
    usage = database.get_user_usage_info(tg_id)
    return {
        "id": user.id,
        "telegramId": user.telegramId,
        "username": user.username,
        "isPro": user.isPro,
        "tier": user.subscription_tier or "free",
        "used": usage['used'],
        "limit": usage['limit']
    }

@app.get("/api/queue/{tg_id}", response_model=List[QueueItem])
async def get_user_queue(tg_id: int):
    user = database.get_user_by_tg_id(tg_id)
    if not user: return []
    
    db = database.SessionLocal()
    try:
        posts = db.query(database.Queue).filter(
            database.Queue.owner_id == user.id, 
            database.Queue.status == 'pending'
        ).order_by(database.Queue.scheduled_time.asc()).all()
        
        return [{
            "id": p.id,
            "text": p.text,
            "photo_id": p.photo_id,
            "status": p.status,
            "scheduled_time": p.scheduled_time,
            "channel": p.channel_id
        } for p in posts]
    finally:
        db.close()

@app.delete("/api/queue/{post_id}")
async def delete_post(post_id: int, tg_id: int):
    # Проверка владельца (безопасность)
    user = database.get_user_by_tg_id(tg_id)
    db = database.SessionLocal()
    try:
        post = db.query(database.Queue).filter(database.Queue.id == post_id, database.Queue.owner_id == user.id).first()
        if post:
            db.delete(post)
            db.commit()
            return {"status": "ok"}
        raise HTTPException(status_code=403, detail="Not authorized or post not found")
    finally:
        db.close()

@app.get("/api/admin/stats")
async def get_admin_stats(tg_id: int):
    if tg_id not in config.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin only")
    return database.get_global_stats()

# --- RUNNER ---
def run_api():
    port = int(os.getenv("PORT", 8000))
    print(f"📡 API Server starting on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

import os
