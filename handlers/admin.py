import re
import logging
import string
import random
import os
import shutil
import time
import httpx
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

import database
from config import (
    ADMIN_IDS, 
    EDIT_INPUT, 
    GEN_DURATION, 
    DELETE_INPUT, 
    UPLOAD_ASSETS, 
    UPLOAD_KEY_TARGET, 
    SHORTEN_INPUT,
    SHORTNER_API,
    STORAGE_DIR
)

# =========================
# HELPERS
# =========================

def delete_code_assets(code):
    """Permanently removes filesystem assets associated with a license key."""
    folder_path = os.path.join(STORAGE_DIR, code)
    zip_path = os.path.join(STORAGE_DIR, f"{code}.zip")
    
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
    if os.path.exists(zip_path):
        os.remove(zip_path)

# =========================
# ADMIN UI
# =========================

async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return

    help_text = "<b>Admin Control Panel</b>\n\nSelect an operation from the options below."
    keyboard = [
        [InlineKeyboardButton("Edit Responses", callback_data="admin_edit_list")],
        [InlineKeyboardButton("Generate License Keys", callback_data="admin_gen_init")],
        [InlineKeyboardButton("Upload Assets to Key", callback_data="admin_upload_init")],
        [InlineKeyboardButton("Link Shortener", callback_data="admin_shorten_init")],
        [InlineKeyboardButton("Manage Database & Files", callback_data="admin_db_manage")],
        [InlineKeyboardButton("Broadcast System", callback_data="admin_broadcast_help")],
        [InlineKeyboardButton("Service Statistics", callback_data="admin_stats")],
    ]
    
    if update.callback_query:
        await update.callback_query.message.edit_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# CALLBACK HANDLER
# =========================

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS: return
    
    await query.answer()
    data = query.data

    # Main Navigation
    if data == "admin_main":
        await admin_help(update, context)

    # 1. Edit Responses
    elif data == "admin_edit_list":
        keyboard = [[InlineKeyboardButton(k, callback_data=f"edit_select_{k}")] for k in database.responses.keys()]
        keyboard.append([InlineKeyboardButton("Cancel", callback_data="admin_main")])
        await query.message.edit_text("<b>Response Configuration</b>\n\nSelect a parameter to modify.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    # 2. License Generation
    elif data == "admin_gen_init":
        keyboard = [
            [InlineKeyboardButton("➕ Generate New Codes", callback_data="admin_gen_params")],
            [InlineKeyboardButton("Return", callback_data="admin_main")]
        ]
        await query.message.edit_text(
            "<b>License Generation Protocol</b>\n\nExisting keys will be preserved. Use the Management menu for cleanup.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_gen_params":
        await query.message.edit_text(
            "<b>Key Generation Configuration</b>\n\nPlease provide parameters: <code>[qty] [duration] [limit]</code>\n\n"
            "Example: <code>10 24hr 5</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_main")]])
        )
        return GEN_DURATION

    # 3. Asset Upload
    elif data == "admin_upload_init":
        context.user_data["temp_assets"] = []
        await query.message.edit_text(
            "<b>Asset Upload Protocol</b>\n\nPlease send the files you wish to associate with a license key.\n\n"
            "Press 'Next' when finished.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next: Specify Key", callback_data="admin_upload_specify")]])
        )
        return UPLOAD_ASSETS

    elif data == "admin_upload_specify":
        if not context.user_data.get("temp_assets"):
            await query.message.edit_text("⚠️ <b>No Assets Detected</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_upload_init")]]))
            return ConversationHandler.END
        await query.message.edit_text("<b>Key Association</b>\n\nEnter the License Key for these assets:", parse_mode="HTML")
        return UPLOAD_KEY_TARGET

    # 4. Link Shortener
    elif data == "admin_shorten_init":
        if not SHORTNER_API:
            await query.message.edit_text("❌ <b>Configuration Error</b>\nShortener API key not found in system environment.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))
            return ConversationHandler.END
        
        await query.message.edit_text(
            "<b>Link Shortener Protocol</b>\n\nPlease provide the destination URL you wish to compress.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_main")]])
        )
        return SHORTEN_INPUT

    # 5. Database & Storage Management
    elif data == "admin_db_manage":
        keyboard = [
            [InlineKeyboardButton("📋 View All Active Keys", callback_data="admin_db_view")],
            [InlineKeyboardButton("🗑 Wipe Entire Database", callback_data="admin_gen_wipe")],
            [InlineKeyboardButton("🧹 Prune Expired/Finished", callback_data="admin_db_prune")],
            [InlineKeyboardButton("❌ Delete Specific Key", callback_data="admin_db_delete_init")],
            [InlineKeyboardButton("Return", callback_data="admin_main")]
        ]
        await query.message.edit_text("<b>Database & Storage Management</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_db_view":
        if not database.codes:
            await query.message.edit_text("<b>No active keys found.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_db_manage")]]))
            return

        current_time = time.time()
        report = "<b>Active License Inventory</b>\n\n"
        for code, details in database.codes.items():
            expired = current_time > details["expiry"]
            used = len(details.get("redeemed_by", []))
            limit = details.get("limit", 1)
            status = "🔴 Expired" if expired else ("⚪ Full" if used >= limit else "🟢 Active")
            report += f"🔑 <code>{code}</code> ({used}/{limit})\n└ Status: {status}\n\n"
            if len(report) > 3800: break
        await query.message.edit_text(report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_db_manage")]]))

    elif data == "admin_gen_wipe":
        count = len(database.codes)
        for code in list(database.codes.keys()): delete_code_assets(code)
        database.codes = {}; database.save_codes()
        await query.message.edit_text(f"✅ <b>Database Purged</b> (Removed {count} keys)", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

    elif data == "admin_db_prune":
        current_time = time.time()
        to_delete = [c for c, d in database.codes.items() if current_time > d["expiry"] or len(d.get("redeemed_by", [])) >= d.get("limit", 1)]
        for code in to_delete: delete_code_assets(code); del database.codes[code]
        database.save_codes()
        await query.message.edit_text(f"🧹 <b>Pruned {len(to_delete)} keys.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

    elif data == "admin_db_delete_init":
        await query.message.edit_text("<b>Enter Key to Delete:</b>", parse_mode="HTML")
        return DELETE_INPUT

    # 5. Broadcast & Stats
    elif data == "admin_broadcast_help":
        await query.message.edit_text("<b>Broadcast System</b>\n\n/broadcast [text] or reply to media.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

    elif data == "admin_stats":
        text = f"<b>Statistics</b>\n\nUsers: <code>{len(database.users)}</code>\nKeys: <code>{len(database.codes)}</code>"
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

# =========================
# INPUT HANDLERS
# =========================

async def edit_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS: return
    await query.answer()
    key = query.data.replace("edit_select_", "")
    context.user_data["editing_key"] = key
    await query.message.edit_text(f"✏️ <b>Editing:</b> <code>{key}</code>\n\nSend new HTML content.", parse_mode="HTML")
    return EDIT_INPUT

async def edit_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    key = context.user_data.get("editing_key")
    if not key: return ConversationHandler.END
    content = update.message.text
    try:
        await update.message.reply_text(f"<b>Preview:</b>\n{content}", parse_mode="HTML")
        database.responses[key] = content
        database.save_responses()
        await update.message.reply_text("✅ <b>Saved.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ <b>HTML Error:</b>\n{str(e)}", parse_mode="HTML")
        return EDIT_INPUT
    return ConversationHandler.END

async def gen_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    args = update.message.text.lower().strip().split()
    if len(args) < 3: return GEN_DURATION
    try:
        qty, duration_str, limit = int(args[0]), args[1], int(args[2])
        match = re.match(r"(\d+)\s*(hr|d|w|m)", duration_str)
        num, unit = int(match.group(1)), match.group(2)
        delta = timedelta(hours=num) if unit=="hr" else (timedelta(days=num) if unit=="d" else (timedelta(weeks=num) if unit=="w" else timedelta(days=num*30)))
        expiry = (datetime.now() + delta).timestamp()
    except: return GEN_DURATION

    keys = []
    for _ in range(qty):
        k = "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
        keys.append(k)
        database.codes[k] = {"expiry": expiry, "limit": limit, "redeemed_by": []}
        os.makedirs(os.path.join(STORAGE_DIR, k), exist_ok=True)
    database.save_codes()
    await update.message.reply_text(f"✅ <b>Generated {qty} keys.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))
    return ConversationHandler.END

async def delete_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    code = update.message.text.strip().upper()
    if code in database.codes:
        delete_code_assets(code); del database.codes[code]; database.save_codes()
        await update.message.reply_text(f"✅ <b>Deleted {code}.</b>", parse_mode="HTML")
    return ConversationHandler.END

async def asset_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    file = update.message.document or (update.message.photo[-1] if update.message.photo else update.message.video)
    if not file: return UPLOAD_ASSETS
    f_info = await file.get_file()
    name = getattr(file, 'file_name', f"file_{int(time.time())}")
    path = os.path.join("temp_uploads", name)
    os.makedirs("temp_uploads", exist_ok=True)
    await f_info.download_to_drive(path)
    if "temp_assets" not in context.user_data: context.user_data["temp_assets"] = []
    context.user_data["temp_assets"].append(path)
    await update.message.reply_text(f"📥 <b>Buffered:</b> {name}", parse_mode="HTML")
    return UPLOAD_ASSETS

async def asset_key_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    code = update.message.text.strip().upper()
    if code not in database.codes: return UPLOAD_KEY_TARGET
    target_dir = os.path.join(STORAGE_DIR, code)
    os.makedirs(target_dir, exist_ok=True)
    assets = context.user_data.pop("temp_assets", [])
    for src in assets: shutil.move(src, os.path.join(target_dir, os.path.basename(src)))
    zip_p = os.path.join(STORAGE_DIR, f"{code}.zip")
    if os.path.exists(zip_p): os.remove(zip_p)
    await update.message.reply_text(f"✅ <b>Assets deployed to {code}.</b>", parse_mode="HTML")
    return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await admin_help(update, context)
    return ConversationHandler.END

async def shorten_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    long_url = update.message.text.strip()
    
    # Improved URL validation using regex
    url_pattern = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    if not re.match(url_pattern, long_url):
        await update.message.reply_text(
            "❌ <b>Validation Error</b>\nThe provided text does not appear to be a valid URL. Please include the protocol (e.g., https://).", 
            parse_mode="HTML"
        )
        return SHORTEN_INPUT

    status_msg = await update.message.reply_text("⏳ <b>Processing Request...</b>", parse_mode="HTML")

    try:
        api_url = f"https://shrinkearn.com/api?api={SHORTNER_API}&url={long_url}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            result = response.json()

        if result.get("status") == "error":
            await status_msg.edit_text(f"❌ <b>API Rejected Request:</b>\n{result.get('message', 'No details provided.')}", parse_mode="HTML")
        else:
            short_url = result.get("shortenedUrl")
            await status_msg.edit_text(
                f"✅ <b>Link Compressed Successfully</b>\n\n"
                f"<b>Original:</b> {long_url}\n"
                f"<b>Shortened:</b> <code>{short_url}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Admin", callback_data="admin_main")]])
            )
    except httpx.HTTPStatusError as e:
        await status_msg.edit_text(f"❌ <b>HTTP Error:</b> {e.response.status_code}", parse_mode="HTML")
    except Exception as e:
        logging.error(f"Shortener Error: {str(e)}")
        await status_msg.edit_text(f"❌ <b>System Exception:</b>\nAn unexpected error occurred during processing.", parse_mode="HTML")
    
    return ConversationHandler.END

# =========================
# BROADCAST & REPLY
# =========================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    target = update.message.reply_to_message
    payload = " ".join(context.args)
    if not target and not payload: return
    sent = 0
    for uid in database.users:
        try:
            if target: await context.bot.copy_message(uid, update.message.chat_id, target.message_id)
            else: await context.bot.send_message(uid, payload, parse_mode="HTML")
            sent += 1
        except: pass
    await update.message.reply_text(f"✅ <b>Sent to {sent} users.</b>", parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides system statistics via command."""
    if update.effective_user.id not in ADMIN_IDS: return
    text = f"<b>Service Statistics</b>\n\nTotal Registered Users: <code>{len(database.users)}</code>\nActive License Keys: <code>{len(database.codes)}</code>"
    await update.message.reply_text(text, parse_mode="HTML")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS or not update.message.reply_to_message: return
    match = re.search(r"\(ID: (\d+)\)", update.message.reply_to_message.text or "")
    if match:
        await context.bot.send_message(int(match.group(1)), f"💬 <b>Admin reply:</b>\n{update.message.text}", parse_mode="HTML")
        await update.message.reply_text("✅ <b>Reply sent.</b>", parse_mode="HTML")
