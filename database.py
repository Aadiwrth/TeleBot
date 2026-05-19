import sqlite3
import json
import os
import shutil
import time
import logging
from config import RESPONSES_FILE, USERS_FILE, DEFAULT_RESPONSES, CODES_FILE, STORAGE_DIR, STOCK_DIR, DB_DIR, DB_FILE

CACHE_FILE = "cache.json"

# =========================
# DATABASE INITIALIZATION
# =========================

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL") # Better concurrency for dashboard
    return conn

def init_db():
    # Ensure database folder exists
    os.makedirs(DB_DIR, exist_ok=True)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Responses Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            key TEXT PRIMARY KEY,
            content TEXT
        )
    """)
    
    # 2. Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            referrals INTEGER DEFAULT 0,
            joined_at REAL
        )
    """)
    
    # 3. Codes Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            expiry REAL,
            usage_limit INTEGER,
            type TEXT,
            content TEXT,
            used BOOLEAN DEFAULT 0
        )
    """)
    
    # 4. Redemptions Table (For better tracking)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            code TEXT,
            redeemed_at REAL,
            UNIQUE(user_id, code)
        )
    """)
    
    # 5. Cache Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # 6. Point Shop Services
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS point_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            cost_per_unit INTEGER,
            description TEXT,
            delete_on_redeem BOOLEAN DEFAULT 1
        )
    """)
    
    # Handle migration for existing databases
    try:
        cursor.execute("ALTER TABLE point_services ADD COLUMN delete_on_redeem BOOLEAN DEFAULT 1")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    # 7. Point Shop Inventory (Stock)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS point_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER,
            content TEXT,
            added_at REAL,
            FOREIGN KEY(service_id) REFERENCES point_services(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()

# =========================
# DATA COMPATIBILITY LAYER
# =========================
# These globals will stay for now to minimize handler changes, 
# but they will be synced with SQLite.

responses = {}
users = {}
codes = {}
cache = {}

def load_data():
    global responses, users, codes, cache
    
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(STOCK_DIR, exist_ok=True)
    os.makedirs("temp_uploads", exist_ok=True)
    
    init_db()
    
    # Check for legacy JSON data to migrate
    if os.path.exists(RESPONSES_FILE) or os.path.exists(USERS_FILE):
        migrate_json_to_sqlite()
        
    sync_globals()

def sync_globals():
    global responses, users, codes, cache
    conn = get_db()
    
    # Load Responses
    res = conn.execute("SELECT * FROM responses").fetchall()
    responses = {row['key']: row['content'] for row in res}
    if not responses:
        responses = DEFAULT_RESPONSES
        save_responses()

    # Load Users
    usr = conn.execute("SELECT * FROM users").fetchall()
    users = {row['user_id']: {
        "username": row['username'],
        "points": row['points'],
        "referred_by": row['referred_by'],
        "referrals": row['referrals'],
        "joined_at": row['joined_at']
    } for row in usr}

    # Load Codes
    cde = conn.execute("SELECT * FROM codes").fetchall()
    codes = {}
    for row in cde:
        redemptions = conn.execute("SELECT user_id FROM redemptions WHERE code = ?", (row['code'],)).fetchall()
        codes[row['code']] = {
            "expiry": row['expiry'],
            "limit": row['usage_limit'],
            "type": row['type'],
            "content": row['content'],
            "used": bool(row['used']),
            "redeemed_by": [r['user_id'] for r in redemptions]
        }

    # Load Cache
    cch = conn.execute("SELECT * FROM cache").fetchall()
    cache = {row['key']: row['value'] for row in cch}
    
    conn.close()

def migrate_json_to_sqlite():
    logging.info("Migrating legacy JSON data to SQLite...")
    conn = get_db()
    
    # Migrate Responses
    if os.path.exists(RESPONSES_FILE):
        with open(RESPONSES_FILE, "r") as f:
            data = json.load(f)
            for k, v in data.items():
                conn.execute("INSERT OR REPLACE INTO responses (key, content) VALUES (?, ?)", (k, v))
        os.rename(RESPONSES_FILE, RESPONSES_FILE + ".bak")

    # Migrate Users
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            data = json.load(f)
            for uid, info in data.items():
                if isinstance(info, str): info = {"username": info}
                conn.execute("""
                    INSERT OR REPLACE INTO users (user_id, username, points, referred_by, referrals, joined_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (uid, info.get("username"), info.get("points", 0), info.get("referred_by"), info.get("referrals", 0), info.get("joined_at", time.time())))
        os.rename(USERS_FILE, USERS_FILE + ".bak")

    # Migrate Codes
    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, "r") as f:
            data = json.load(f)
            for code, info in data.items():
                conn.execute("""
                    INSERT OR REPLACE INTO codes (code, expiry, usage_limit, type, content, used)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (code, info.get("expiry"), info.get("limit", 1), info.get("type", "asset"), info.get("content"), info.get("used", 0)))
                
                for uid in info.get("redeemed_by", []):
                    conn.execute("INSERT OR IGNORE INTO redemptions (user_id, code, redeemed_at) VALUES (?, ?, ?)", (str(uid), code, time.time()))
        os.rename(CODES_FILE, CODES_FILE + ".bak")

    conn.commit()
    conn.close()
    logging.info("Migration complete. Legacy files backed up.")

# =========================
# SAVE METHODS (Wrapper)
# =========================

def save_responses():
    conn = get_db()
    for k, v in responses.items():
        conn.execute("INSERT OR REPLACE INTO responses (key, content) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def update_response(key, content):
    """Targeted update for a single response."""
    global responses
    responses[key] = content
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO responses (key, content) VALUES (?, ?)", (key, content))
    conn.commit()
    conn.close()

def save_users():
    """DEPRECATED: Use update_user instead for performance."""
    conn = get_db()
    for uid, info in users.items():
        if not isinstance(info, dict): continue
        conn.execute("""
            INSERT OR REPLACE INTO users (user_id, username, points, referred_by, referrals, joined_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (uid, info.get("username"), info.get("points", 0), info.get("referred_by"), info.get("referrals", 0), info.get("joined_at", info.get("joined_at", time.time()))) )
    conn.commit()
    conn.close()

def update_user(user_id, **kwargs):
    """Targeted update for a single user."""
    uid_str = str(user_id)
    if uid_str not in users:
        return False
    
    for k, v in kwargs.items():
        users[uid_str][k] = v
        
    info = users[uid_str]
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO users (user_id, username, points, referred_by, referrals, joined_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (uid_str, info.get("username"), info.get("points", 0), info.get("referred_by"), info.get("referrals", 0), info.get("joined_at", time.time())))
    conn.commit()
    conn.close()
    return True

def save_codes():
    """DEPRECATED: Use update_code instead for performance."""
    conn = get_db()
    for code, info in codes.items():
        if not isinstance(info, dict): continue
        conn.execute("""
            INSERT OR REPLACE INTO codes (code, expiry, usage_limit, type, content, used)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, info.get("expiry"), info.get("limit", 1), info.get("type", info.get("type", "asset")), info.get("content"), 1 if info.get("used") else 0))
        
        # Sync redemptions
        redeemed_by = info.get("redeemed_by", [])
        if redeemed_by:
            for uid in redeemed_by:
                conn.execute("INSERT OR IGNORE INTO redemptions (user_id, code, redeemed_at) VALUES (?, ?, ?)", (str(uid), code, time.time()))
    
    conn.commit()
    conn.close()

def update_code(code, **kwargs):
    """Targeted update for a single code."""
    if code not in codes:
        return False
        
    for k, v in kwargs.items():
        codes[code][k] = v
        
    info = codes[code]
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO codes (code, expiry, usage_limit, type, content, used)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (code, info.get("expiry"), info.get("limit", 1), info.get("type", info.get("type", "asset")), info.get("content"), 1 if info.get("used") else 0))
    
    # Sync redemptions if provided in kwargs or if we want to be safe
    if "redeemed_by" in kwargs:
        for uid in kwargs["redeemed_by"]:
            conn.execute("INSERT OR IGNORE INTO redemptions (user_id, code, redeemed_at) VALUES (?, ?, ?)", (str(uid), code, time.time()))
            
    conn.commit()
    conn.close()
    return True

def save_cache():
    """DEPRECATED: Use update_cache instead."""
    conn = get_db()
    for k, v in cache.items():
        conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()

def update_cache(key, value):
    """Targeted update for a single cache entry."""
    global cache
    cache[key] = value
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# =========================
# UTILITIES
# =========================

def get_user_mention(user_id):
    uid_str = str(user_id)
    u = users.get(uid_str)
    if u and u.get("username"):
        return u["username"]
    return f"<code>{user_id}</code>"

def delete_code_assets(code):
    folder_path = os.path.join(STORAGE_DIR, code)
    zip_path = os.path.join(STORAGE_DIR, f"{code}.zip")
    if os.path.exists(folder_path): shutil.rmtree(folder_path)
    if os.path.exists(zip_path): os.remove(zip_path)
    
    conn = get_db()
    conn.execute("DELETE FROM codes WHERE code = ?", (code,))
    conn.execute("DELETE FROM redemptions WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    if code in codes: del codes[code]

def initialize_user(user_id, username):
    uid_str = str(user_id)
    is_new = False
    if uid_str not in users:
        is_new = True
        users[uid_str] = {
            "username": username,
            "points": 0,
            "referred_by": None,
            "referrals": 0,
            "joined_at": time.time()
        }
    else:
        users[uid_str]["username"] = username
    
    update_user(user_id)
    return users[uid_str]
