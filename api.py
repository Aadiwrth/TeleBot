from fastapi import FastAPI, Depends, HTTPException, Security, Body, UploadFile, File
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import database
import config
import os
import time
import httpx
import random
import string

app = FastAPI(title="TeleBot Dashboard API")

# Models for Request Bodies
class ResponseUpdate(BaseModel):
    content: str

class KeyGenRequest(BaseModel):
    qty: int
    duration: str # e.g. "24hr", "1d"
    limit: int
    type: str # "asset" or "text"
    custom_key: Optional[str] = None
    content: Optional[str] = None # For text-based keys

class ShortenRequest(BaseModel):
    url: str

# Security
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == config.DASHBOARD_API_KEY:
        return api_key_header
    raise HTTPException(status_code=403, detail="Could not validate credentials")

# CORS (Allow your future React frontend to talk to this API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with your dashboard URL
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "online", "message": "TeleBot Dashboard API is running"}

@app.get("/stats", dependencies=[Depends(get_api_key)])
async def get_stats():
    conn = database.get_db()
    
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_redemptions = conn.execute("SELECT COUNT(*) FROM redemptions").fetchone()[0]
    total_keys = conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0]
    
    # Point Shop Stats
    total_services = conn.execute("SELECT COUNT(*) FROM point_services").fetchone()[0]
    total_stock = conn.execute("SELECT COUNT(*) FROM point_inventory").fetchone()[0]
    
    conn.close()
    
    return {
        "users": total_users,
        "redemptions": total_redemptions,
        "keys": total_keys,
        "shop": {
            "services": total_services,
            "total_stock": total_stock
        }
    }

@app.get("/users", dependencies=[Depends(get_api_key)])
async def get_users():
    conn = database.get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/keys", dependencies=[Depends(get_api_key)])
async def get_keys():
    # Sync memory data with DB info
    result = []
    current_time = time.time()
    for code, details in database.codes.items():
        redemptions = len(details.get("redeemed_by", []))
        limit = details.get("limit", 1)
        
        status = "active"
        if current_time > details["expiry"]:
            status = "expired"
        elif redemptions >= limit:
            status = "full"
            
        result.append({
            "code": code,
            "type": details["type"],
            "usage": f"{redemptions}/{limit}",
            "expiry": details["expiry"],
            "status": status,
            "redemptions": redemptions,
            "limit": limit
        })
    return result

@app.get("/services", dependencies=[Depends(get_api_key)])
async def get_services():
    conn = database.get_db()
    services = conn.execute("SELECT * FROM point_services").fetchall()
    
    result = []
    for s in services:
        stock_count = conn.execute("SELECT COUNT(*) FROM point_inventory WHERE service_id = ?", (s['id'],)).fetchone()[0]
        s_dict = dict(s)
        s_dict['stock_count'] = stock_count
        result.append(s_dict)
        
    conn.close()
    return result

# --- NEW ENDPOINTS ---

@app.get("/responses", dependencies=[Depends(get_api_key)])
async def get_responses():
    return database.responses

@app.put("/responses/{key}", dependencies=[Depends(get_api_key)])
async def update_response(key: str, body: ResponseUpdate):
    if key in database.responses:
        database.responses[key] = body.content
        database.save_responses()
        return {"status": "success", "message": f"Response {key} updated"}
    raise HTTPException(status_code=404, detail="Response key not found")

@app.post("/keys/generate", dependencies=[Depends(get_api_key)])
async def generate_keys(req: KeyGenRequest):
    import re
    from datetime import datetime, timedelta
    
    try:
        match = re.match(r"(\d+)\s*(hr|d|w|m)", req.duration.lower())
        num, unit = int(match.group(1)), match.group(2)
        delta = timedelta(hours=num) if unit=="hr" else (timedelta(days=num) if unit=="d" else (timedelta(weeks=num) if unit=="w" else timedelta(days=num*30)))
        expiry = (datetime.now() + delta).timestamp()
    except:
        raise HTTPException(status_code=400, detail="Invalid duration format. Use e.g. '24hr', '7d'")

    keys_created = []
    for _ in range(req.qty):
        if req.custom_key and req.qty == 1:
            k = req.custom_key.strip().upper()
        else:
            k = "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
        
        database.codes[k] = {
            "expiry": expiry, 
            "limit": req.limit, 
            "redeemed_by": [], 
            "type": req.type,
            "content": req.content if req.type == "text" else None,
            "used": False
        }
        if req.type == "asset":
            os.makedirs(os.path.join(config.STORAGE_DIR, k), exist_ok=True)
        keys_created.append(k)
    
    database.save_codes()
    return {"status": "success", "keys": keys_created}

@app.post("/tools/shorten", dependencies=[Depends(get_api_key)])
async def shorten_link(req: ShortenRequest):
    if not config.SHORTNER_API:
        raise HTTPException(status_code=500, detail="Shortener API key not configured in bot")
    
    api_url = f"https://shrinkearn.com/api?api={config.SHORTNER_API}&url={req.url}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(api_url)
        result = response.json()

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "API Error"))
    
    return {"shortened_url": result.get("shortenedUrl")}

@app.delete("/keys/{code}", dependencies=[Depends(get_api_key)])
async def delete_key(code: str):
    if code in database.codes:
        database.delete_code_assets(code)
        database.save_codes()
        return {"status": "success", "message": f"Key {code} deleted"}
    raise HTTPException(status_code=404, detail="Key not found")

# --- FILE UPLOAD ENDPOINTS ---

@app.post("/keys/{code}/assets", dependencies=[Depends(get_api_key)])
async def upload_key_assets(code: str, files: List[UploadFile] = File(...)):
    if code not in database.codes:
        raise HTTPException(status_code=404, detail="Key not found")
    
    target_dir = os.path.join(config.STORAGE_DIR, code)
    os.makedirs(target_dir, exist_ok=True)
    
    for file in files:
        file_path = os.path.join(target_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
    # Refresh ZIP cache
    zip_p = os.path.join(config.STORAGE_DIR, f"{code}.zip")
    if os.path.exists(zip_p): os.remove(zip_p)
    
    return {"status": "success", "count": len(files)}

@app.post("/services/{service_id}/stock", dependencies=[Depends(get_api_key)])
async def upload_service_stock(service_id: int, files: List[UploadFile] = File(...)):
    conn = database.get_db()
    service = conn.execute("SELECT name FROM point_services WHERE id = ?", (service_id,)).fetchone()
    if not service:
        conn.close()
        raise HTTPException(status_code=404, detail="Service not found")
        
    service_name_safe = service['name'].replace(" ", "_")
    target_dir = os.path.join(config.STOCK_DIR, service_name_safe)
    os.makedirs(target_dir, exist_ok=True)
    
    count = 0
    for file in files:
        # We only care about filename, doesn't HAVE to be .txt but user requested multiple txt
        unique_name = f"{int(time.time())}_{random.randint(1000, 9999)}_{file.filename}"
        file_path = os.path.join(target_dir, unique_name)
        
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        conn.execute("INSERT INTO point_inventory (service_id, content, added_at) VALUES (?, ?, ?)", 
                     (service_id, unique_name, time.time()))
        count += 1
        
    conn.commit()
    conn.close()
    return {"status": "success", "count": count}
