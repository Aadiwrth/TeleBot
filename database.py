import json
import os
import shutil
from config import RESPONSES_FILE, USERS_FILE, DEFAULT_RESPONSES, CODES_FILE, STORAGE_DIR

CACHE_FILE = "cache.json"

# =========================
# DATA STORAGE
# =========================

responses = {}
users = {}
codes = {}
cache = {}

def load_data():
    global responses, users, codes, cache
    
    # Ensure directories exist
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs("temp_uploads", exist_ok=True)
    
    if os.path.exists(RESPONSES_FILE):
        with open(RESPONSES_FILE, "r") as f:
            responses = json.load(f)
    else:
        responses = DEFAULT_RESPONSES
        save_responses()

    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            raw_users = json.load(f)
            if isinstance(raw_users, list):
                # Migration: Convert list of IDs to dict
                users = {str(uid): str(uid) for uid in raw_users}
            else:
                users = raw_users
    else:
        users = {}

    if os.path.exists(CODES_FILE):
        with open(CODES_FILE, "r") as f:
            codes = json.load(f)
    else:
        codes = {}

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache = json.load(f)
    else:
        cache = {}

def save_responses():
    with open(RESPONSES_FILE, "w") as f:
        json.dump(responses, f, indent=4)

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

def save_codes():
    with open(CODES_FILE, "w") as f:
        json.dump(codes, f, indent=4)

def save_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_user_mention(user_id):
    """Returns @username or ID if not found."""
    uid_str = str(user_id)
    return users.get(uid_str, f"<code>{user_id}</code>")

def delete_code_assets(code):
    """Permanently removes filesystem assets associated with a license key."""
    folder_path = os.path.join(STORAGE_DIR, code)
    zip_path = os.path.join(STORAGE_DIR, f"{code}.zip")
    
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
    if os.path.exists(zip_path):
        os.remove(zip_path)
