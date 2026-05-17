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
    GEN_TYPE,
    GEN_PARAMS,
    GEN_CONTENT_STEP,
    DELETE_INPUT, 
    UPLOAD_ASSETS, 
    UPLOAD_KEY_TARGET, 
    SHORTEN_INPUT,
    SEARCH_INPUT,
    REPLY_INPUT,
    SHORTNER_API,
    STORAGE_DIR
)

# =========================
# HELPERS
# =========================

async def get_detailed_stats():
    """Generates a comprehensive system performance report."""
    current_time = time.time()
    total_users = len(database.users)
    total_keys = len(database.codes)
    
    active_keys = 0
    expired_keys = 0
    full_keys = 0
    total_redemptions = 0
    unique_redeemers = set()
    redeemer_counts = {}
    
    for code, details in database.codes.items():
        redemptions = details.get("redeemed_by", [])
        total_redemptions += len(redemptions)
        for uid in redemptions:
            uid_str = str(uid)
            unique_redeemers.add(uid_str)
            redeemer_counts[uid_str] = redeemer_counts.get(uid_str, 0) + 1
            
        is_expired = current_time > details["expiry"]
        is_full = len(redemptions) >= details.get("limit", 1)
        
        if is_expired:
            expired_keys += 1
        elif is_full:
            full_keys += 1
        else:
            active_keys += 1
            
    report = (
        "📊 <b>System Performance Dashboard</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👥 <b>User Base</b>\n"
        f"├ Total Registered: <code>{total_users}</code>\n"
        f"└ Unique Redeemers: <code>{len(unique_redeemers)}</code>\n\n"
        "🔑 <b>License Inventory</b>\n"
        f"├ Total Generated: <code>{total_keys}</code>\n"
        f"├ 🟢 Active/Valid: <code>{active_keys}</code>\n"
        f"├ ⚪ Fully Redeemed: <code>{full_keys}</code>\n"
        f"└ 🔴 Expired: <code>{expired_keys}</code>\n\n"
        "📈 <b>Activity Metrics</b>\n"
        f"└ Total Deliveries: <code>{total_redemptions}</code>\n"
    )

    top_redeemers = sorted(redeemer_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    if top_redeemers:
        report += "\n🏆 <b>Top Power Users</b>\n"
        for i, (uid, count) in enumerate(top_redeemers, 1):
            mention = database.get_user_mention(uid)
            report += f"{i}. {mention} — <code>{count} keys</code>\n"

    report += "\n━━━━━━━━━━━━━━━━━━━━\n"
    report += f"<i>Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
    
    return report

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
            [
                InlineKeyboardButton("📂 Asset-based", callback_data="admin_gen_type_asset"),
                InlineKeyboardButton("📝 Text-based", callback_data="admin_gen_type_text")
            ],
            [InlineKeyboardButton("Return", callback_data="admin_main")]
        ]
        await query.message.edit_text(
            "<b>License Generation Protocol</b>\n\nSelect the delivery format for this batch:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return GEN_TYPE

    elif data.startswith("admin_gen_type_"):
        g_type = data.replace("admin_gen_type_", "")
        context.user_data["gen_type"] = g_type
        await query.message.edit_text(
            f"<b>Batch Configuration ({g_type.title()})</b>\n\nPlease provide parameters: <code>[qty] [duration] [limit]</code>\n\n"
            "Example: <code>10 24hr 5</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_main")]])
        )
        return GEN_PARAMS

    # 3. Asset Upload (Sequential step)
    elif data == "admin_gen_step_next":
        return await admin_gen_step_next_callback(update, context)

    # Asset Upload (Standalone)
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
            [InlineKeyboardButton("🔍 Advanced Search", callback_data="admin_db_search_init")],
            [InlineKeyboardButton("🗑 Wipe Entire Database", callback_data="admin_gen_wipe")],
            [InlineKeyboardButton("🧹 Prune Expired/Finished", callback_data="admin_db_prune")],
            [InlineKeyboardButton("❌ Delete Specific Key", callback_data="admin_db_delete_init")],
            [InlineKeyboardButton("Return", callback_data="admin_main")]
        ]
        await query.message.edit_text("<b>Database & Storage Management</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "admin_db_search_init":
        await query.message.edit_text(
            "<b>Advanced Lookup System</b>\n\nPlease provide a <b>License Key</b> or <b>User ID</b> to retrieve detailed history.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_db_manage")]])
        )
        return SEARCH_INPUT

    elif data == "admin_db_view":
        if not database.codes:
            await query.message.edit_text("<b>No active keys found.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_db_manage")]]))
            return

        current_time = time.time()
        report = "<b>Active License Inventory</b>\n\n"
        for code, details in database.codes.items():
            expired = current_time > details["expiry"]
            redeemed_list = details.get("redeemed_by", [])
            used = len(redeemed_list)
            limit = details.get("limit", 1)
            status = "🔴 Expired" if expired else ("⚪ Full" if used >= limit else "🟢 Active")
            
            report += f"🔑 <code>{code}</code> ({used}/{limit})\n└ Status: {status}\n"
            if redeemed_list:
                users_str = ", ".join([database.get_user_mention(uid) for uid in redeemed_list])
                report += f"└ Redeemed by: {users_str}\n"
            report += "\n"
            
            if len(report) > 3800: break
        await query.message.edit_text(report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_db_manage")]]))

    elif data == "admin_gen_wipe":
        count = len(database.codes)
        for code in list(database.codes.keys()): database.delete_code_assets(code)
        database.codes = {}; database.save_codes()
        await query.message.edit_text(f"✅ <b>Database Purged</b> (Removed {count} keys)", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

    elif data == "admin_db_prune":
        current_time = time.time()
        to_delete = [c for c, d in database.codes.items() if current_time > d["expiry"] or len(d.get("redeemed_by", [])) >= d.get("limit", 1)]
        for code in to_delete: database.delete_code_assets(code); del database.codes[code]
        database.save_codes()
        await query.message.edit_text(f"🧹 <b>Pruned {len(to_delete)} keys.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

    elif data == "admin_db_delete_init":
        await query.message.edit_text("<b>Enter Key to Delete:</b>", parse_mode="HTML")
        return DELETE_INPUT

    # 5. Broadcast & Stats
    elif data == "admin_broadcast_help":
        await query.message.edit_text("<b>Broadcast System</b>\n\n/broadcast [text] or reply to media.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))

    elif data == "admin_stats":
        report = await get_detailed_stats()
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="admin_stats")],
            [InlineKeyboardButton("Return", callback_data="admin_main")]
        ]
        await query.message.edit_text(report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

    # Support Reply
    elif data.startswith("admin_reply_init_"):
        return await admin_reply_init(update, context)

    # Proof Verification
    elif data.startswith("admin_proof_"):
        parts = data.split("_")
        action = parts[2] # approve or reject
        target_uid = int(parts[3])
        target_code = parts[4]
        
        if action == "approve":
            await context.bot.send_message(target_uid, f"✅ <b>Proof Approved</b>\nYour redemption for key <code>{target_code}</code> has been verified. Thank you!", parse_mode="HTML")
            await query.message.edit_caption(caption=query.message.caption + "\n\n✅ <b>Approved</b>", parse_mode="HTML")
        else:
            await context.bot.send_message(target_uid, f"❌ <b>Proof Rejected</b>\nYour submission for key <code>{target_code}</code> was found invalid. Please contact support if this is an error.", parse_mode="HTML")
            await query.message.edit_caption(caption=query.message.caption + "\n\n❌ <b>Rejected</b>", parse_mode="HTML")

# =========================
# INPUT HANDLERS
# =========================

async def handle_smart_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles direct asset upload via caption outside conversation."""
    if update.effective_user.id not in ADMIN_IDS: return
    
    caption = update.message.caption.strip().upper() if update.message.caption else None
    if not caption or caption not in database.codes:
        return # Not a smart upload target
    
    file = update.message.document or (update.message.photo[-1] if update.message.photo else update.message.video)
    if not file: return

    try:
        f_info = await file.get_file()
        name = getattr(file, 'file_name', f"file_{int(time.time())}")
        
        target_dir = os.path.join(STORAGE_DIR, caption)
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, name)
        await f_info.download_to_drive(path)
        
        # Refresh ZIP
        zip_p = os.path.join(STORAGE_DIR, f"{caption}.zip")
        if os.path.exists(zip_p): os.remove(zip_p)
        
        await update.message.reply_text(f"🚀 <b>Smart Association Successful</b>\nAsset: <code>{name}</code>\nTarget Key: <code>{caption}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Upload Error:</b> {str(e)}", parse_mode="HTML")

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

async def gen_params_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    args = update.message.text.lower().strip().split()
    if len(args) < 3: return GEN_PARAMS
    try:
        qty, duration_str, limit = int(args[0]), args[1], int(args[2])
        match = re.match(r"(\d+)\s*(hr|d|w|m)", duration_str)
        num, unit = int(match.group(1)), match.group(2)
        delta = timedelta(hours=num) if unit=="hr" else (timedelta(days=num) if unit=="d" else (timedelta(weeks=num) if unit=="w" else timedelta(days=num*30)))
        expiry = (datetime.now() + delta).timestamp()
    except: return GEN_PARAMS

    g_type = context.user_data.get("gen_type", "asset")
    keys = []
    for _ in range(qty):
        k = "".join(random.choices(string.ascii_uppercase + string.digits, k=12))
        keys.append(k)
        database.codes[k] = {"expiry": expiry, "limit": limit, "redeemed_by": [], "type": g_type}
        if g_type == "asset":
            os.makedirs(os.path.join(STORAGE_DIR, k), exist_ok=True)
    
    database.save_codes()
    context.user_data["pending_keys"] = keys
    context.user_data["processed_keys"] = []
    
    await update.message.reply_text(f"✅ <b>Generated {qty} keys.</b>\n\nStarting sequential content association...", parse_mode="HTML")
    return await next_gen_step(update, context)

async def next_gen_step(update, context):
    pending = context.user_data.get("pending_keys", [])
    g_type = context.user_data.get("gen_type", "asset")
    
    if not pending:
        processed = context.user_data.pop("processed_keys", [])
        keys_formatted = "\n".join([f"<code>{k}</code>" for k in processed])
        text = f"🏁 <b>Batch Generation Complete</b>\n\nAll keys associated with content.\n\n<b>Key List:</b>\n{keys_formatted}"
        
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Admin", callback_data="admin_main")]]))
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Admin", callback_data="admin_main")]]))
        return ConversationHandler.END

    current_key = pending[0]
    
    if g_type == "asset":
        text = f"📤 <b>Asset Association:</b> <code>{current_key}</code>\n\nPlease upload the files for this specific key.\n\nClick 'Done for this Key' when finished."
        keyboard = [[InlineKeyboardButton("✅ Done for this Key", callback_data="admin_gen_step_next")]]
    else:
        text = f"📝 <b>Message Association:</b> <code>{current_key}</code>\n\nPlease send the text content/credentials for this specific key."
        keyboard = []

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return GEN_CONTENT_STEP

async def gen_content_step_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    pending = context.user_data.get("pending_keys", [])
    if not pending: return ConversationHandler.END
    
    current_key = pending[0]
    g_type = context.user_data.get("gen_type", "asset")

    if g_type == "asset":
        file = update.message.document or (update.message.photo[-1] if update.message.photo else update.message.video)
        if not file: return GEN_CONTENT_STEP
        
        f_info = await file.get_file()
        name = getattr(file, 'file_name', f"file_{int(time.time())}")
        target_dir = os.path.join(STORAGE_DIR, current_key)
        os.makedirs(target_dir, exist_ok=True)
        await f_info.download_to_drive(os.path.join(target_dir, name))
        
        # Refresh ZIP cache
        zip_p = os.path.join(STORAGE_DIR, f"{current_key}.zip")
        if os.path.exists(zip_p): os.remove(zip_p)
        
        await update.message.reply_text(f"📥 <b>Buffered to {current_key}:</b> {name}", parse_mode="HTML")
        return GEN_CONTENT_STEP
    else:
        # Text based
        content = update.message.text
        if not content: return GEN_CONTENT_STEP
        
        database.codes[current_key]["content"] = content
        database.save_codes()
        
        # Move to next key immediately for text
        context.user_data["processed_keys"].append(pending.pop(0))
        return await next_gen_step(update, context)

async def admin_gen_step_next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pending = context.user_data.get("pending_keys", [])
    if pending:
        context.user_data["processed_keys"].append(pending.pop(0))
    return await next_gen_step(update, context)

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

async def search_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    query_text = update.message.text.strip().upper()
    
    # 1. Search for Key
    if query_text in database.codes:
        details = database.codes[query_text]
        redeemed_list = details.get("redeemed_by", [])
        report = (
            f"🔍 <b>Key Lookup:</b> <code>{query_text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Expiry:</b> {time.ctime(details['expiry'])}\n"
            f"📊 <b>Usage:</b> {len(redeemed_list)}/{details.get('limit', 1)}\n\n"
            f"👤 <b>Redeemed by:</b>\n" + (", ".join([database.get_user_mention(uid) for uid in redeemed_list]) if redeemed_list else "<i>No redemptions yet.</i>")
        )
        await update.message.reply_text(report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_db_manage")]]))
        return ConversationHandler.END

    # 2. Search for User (if query is a digit)
    if query_text.isdigit():
        uid_str = query_text
        redeemed_keys = [code for code, data in database.codes.items() if int(uid_str) in data.get("redeemed_by", [])]
        mention = database.get_user_mention(uid_str)
        report = (
            f"👤 <b>User Lookup:</b> {mention}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 <b>Redeemed Keys:</b>\n" + (", ".join([f"<code>{k}</code>" for k in redeemed_keys]) if redeemed_keys else "<i>No redemption history found.</i>")
        )
        await update.message.reply_text(report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_db_manage")]]))
        return ConversationHandler.END

    await update.message.reply_text("❌ <b>No match found.</b> Try another key or User ID.", parse_mode="HTML")
    return SEARCH_INPUT

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
            target_id = int(uid)
            if target: await context.bot.copy_message(target_id, update.message.chat_id, target.message_id)
            else: await context.bot.send_message(target_id, payload, parse_mode="HTML")
            sent += 1
        except: pass
    await update.message.reply_text(f"✅ <b>Sent to {sent} users.</b>", parse_mode="HTML")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides system statistics via command."""
    if update.effective_user.id not in ADMIN_IDS: return
    report = await get_detailed_stats()
    await update.message.reply_text(report, parse_mode="HTML")

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS or not update.message.reply_to_message: return
    match = re.search(r"\(ID: (\d+)\)", update.message.reply_to_message.text or "")
    if match:
        await context.bot.send_message(int(match.group(1)), f"💬 <b>Admin reply:</b>\n{update.message.text}", parse_mode="HTML")
        await update.message.reply_text("✅ <b>Reply sent.</b>", parse_mode="HTML")

async def admin_reply_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS: return
    await query.answer()
    
    target_id = query.data.replace("admin_reply_init_", "")
    context.user_data["reply_target_id"] = target_id
    
    await query.message.reply_text(
        f"💬 <b>Replying to User ID:</b> <code>{target_id}</code>\n\nPlease send the message you wish to transmit to this user.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_main")]])
    )
    return REPLY_INPUT

async def admin_reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS: return
    target_id = context.user_data.pop("reply_target_id", None)
    if not target_id: return ConversationHandler.END
    
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"💬 <b>Admin Correspondence</b>\n\n{update.message.text}",
            parse_mode="HTML"
        )
        await update.message.reply_text("✅ <b>Message Transmitted Successfully.</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="admin_main")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Transmission Failed:</b> {str(e)}", parse_mode="HTML")
    
    return ConversationHandler.END
