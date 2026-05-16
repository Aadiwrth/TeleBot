import json
import os
from config import RESPONSES_FILE, USERS_FILE, DEFAULT_RESPONSES, CODES_FILE, STORAGE_DIR

# =========================
# DATA STORAGE
# =========================

responses = {}
users = {}
codes = {}

def load_data():
    global responses, users, codes
    
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

def save_responses():
    with open(RESPONSES_FILE, "w") as f:
        json.dump(responses, f, indent=4)

def save_users():
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

def save_codes():
    with open(CODES_FILE, "w") as f:
        json.dump(codes, f, indent=4)

def get_user_mention(user_id):
    """Returns @username or ID if not found."""
    uid_str = str(user_id)
    return users.get(uid_str, f"<code>{user_id}</code>")
