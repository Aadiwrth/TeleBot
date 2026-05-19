import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "change_me_now_123")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
SHORTNER_API = os.getenv("SHORTNER")

RESPONSES_FILE = "responses.json"
USERS_FILE = "users.json"

FORCE_CHANNELS = [
    "@fgaroyal",
    "@royalfgachat",
    "@proofroyalfga",
]

# Conversation States
EDIT_SELECT, EDIT_INPUT = range(2)
GEN_TYPE = 3
REDEEM_INPUT = 4
DELETE_INPUT = 5
UPLOAD_ASSETS = 6
UPLOAD_KEY_TARGET = 7
CONTACT_INPUT = 8
SHORTEN_INPUT = 9
PROOF_INPUT = 10
SEARCH_INPUT = 11
REPLY_INPUT = 12
GEN_PARAMS = 13
GEN_CONTENT_STEP = 14
ORDER_INPUT = 15

# Point Shop States
POINT_SHOP_SELECT = 16
POINT_QUANTITY_SELECT = 17
ADMIN_POINT_MANAGE = 18
ADMIN_POINT_ADD_SERVICE = 19
ADMIN_POINT_SET_COST = 20
ADMIN_POINT_ADD_STOCK = 21

CODES_FILE = "codes.json"
STORAGE_DIR = "folder_code"
STOCK_DIR = "stock"
DB_DIR = "database"
DB_FILE = os.path.join(DB_DIR, "database.db")

DEFAULT_RESPONSES = {
    "nfcookies": "<b>Netflix Service Configuration</b>\n\n• Single Access (12 Month Warranty): <b>$4.00</b>\n• 5-Unit Bundle: <b>$3.00/unit</b>\n• 10-Unit Bundle: <b>$5.00/unit</b>\n\n<blockquote>Availability: Restricted Stock</blockquote>",

    "order": "<b>Order Processing</b>\n\nTo initiate a transaction, please provide the following details:\n\n1. <b>Service Specification</b>\n2. <b>Quantity</b>\n3. <b>Preferred Payment Method</b>\n4. <b>Verification Contact (Email)</b>\n\n<blockquote>An administrator will review your request and respond within business hours.</blockquote>",

    "googleaipro": "<b>Google AI Professional</b>\n\n• Monthly Access: <b>$10.00</b>\n• Annual Subscription: <b>$80.00</b>\n\n<b>Included Services:</b>\n- Gemini Advanced Integration\n- 2TB Cloud Storage\n- Enhanced Security Protocols",

    "offers": "<b>Promotional Updates</b>\n\nCurrent Rate: <b>$4.00</b> per Netflix Configuration, inclusive of a <u>12-Month Service Warranty</u>.",

    "giveaway": "<b>Scheduled Distributions</b>\n\nPromotional distributions are currently in the planning phase. Notifications will be issued upon activation.",

    "contact": "<b>Support Correspondence</b>\n\nDirect Inquiries: @royal69Anonymous , @fgag3n"
}
