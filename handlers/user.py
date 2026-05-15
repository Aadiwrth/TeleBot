from telegram import Update
from telegram.ext import ContextTypes
import database
from config import ADMIN_IDS

import os
import shutil
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database
from config import ADMIN_IDS, REDEEM_INPUT, STORAGE_DIR, CONTACT_INPUT

async def redeem_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "<b>License Redemption Portal</b>\n\nPlease provide your unique license key to initiate the retrieval process.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="start_main")]])
    )
    return REDEEM_INPUT

async def redeem_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    user_id = update.message.from_user.id
    current_time = time.time()

    # 1. Check existence
    if code not in database.codes:
        await update.message.reply_text("❌ <b>Invalid Specification</b>\nThe provided license key is not recognized by our system.", parse_mode="HTML")
        return ConversationHandler.END

    data = database.codes[code]

    # 2. Check expiry
    if current_time > data["expiry"]:
        await update.message.reply_text("❌ <b>Session Expired</b>\nThis license key has exceeded its validity period and is no longer active.", parse_mode="HTML")
        return ConversationHandler.END

    # 3. Check if user already redeemed this specific key
    if user_id in data.get("redeemed_by", []):
        await update.message.reply_text("⚠️ <b>Redemption Conflict</b>\nYou have already utilized this license key. Duplicate redemptions are restricted.", parse_mode="HTML")
        return ConversationHandler.END

    # 4. Check usage limit
    current_redeems = len(data.get("redeemed_by", []))
    limit = data.get("limit", 1)

    if current_redeems >= limit:
        await update.message.reply_text("❌ <b>Capacity Reached</b>\nThis license key has reached its maximum usage limit and is now invalid.", parse_mode="HTML")
        return ConversationHandler.END

    # 5. Locate and deliver file
    folder_path = os.path.join(STORAGE_DIR, code)
    zip_path = os.path.join(STORAGE_DIR, f"{code}.zip")

    # If ZIP doesn't exist, try to zip the folder content
    if not os.path.exists(zip_path):
        if os.path.exists(folder_path) and os.listdir(folder_path):
            shutil.make_archive(os.path.join(STORAGE_DIR, code), 'zip', folder_path)
        else:
            await update.message.reply_text("⚠️ <b>Asset Unavailable</b>\nThe administrative content for this key has not been uploaded. Please contact support.", parse_mode="HTML")
            return ConversationHandler.END

    try:
        await update.message.reply_document(
            document=open(zip_path, 'rb'),
            caption=(
                "<b>Secure Delivery Successful</b>\n\n"
                f"License Key: <code>{code}</code>\n"
                f"Status: {current_redeems + 1}/{limit} Uses Utilized\n"
                f"Expiry: {time.ctime(data['expiry'])}"
            ),
            parse_mode="HTML"
        )
        
        # Mark as redeemed by this user
        if "redeemed_by" not in database.codes[code]:
            database.codes[code]["redeemed_by"] = []
        
        database.codes[code]["redeemed_by"].append(user_id)
        
        # Mark as 'used' for legacy compatibility if needed, but we rely on len(redeemed_by)
        database.codes[code]["used"] = len(database.codes[code]["redeemed_by"]) >= limit
        
        database.save_codes()
        
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Delivery Failure</b>\nAn internal error occurred during the transmission: {str(e)}", parse_mode="HTML")

    return ConversationHandler.END

# =========================
# CONTACT / SUPPORT SYSTEM
# =========================

async def contact_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["support_msg"] = ""
    
    await query.message.reply_text(
        "<b>Support Correspondence</b>\n\nPlease describe your inquiry or technical issue below. You can send multiple messages to add more detail.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="start_main")]])
    )
    return CONTACT_INPUT

async def contact_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text: return CONTACT_INPUT
    
    current_content = context.user_data.get("support_msg", "")
    context.user_data["support_msg"] = (current_content + "\n" + text).strip()
    
    keyboard = [
        [InlineKeyboardButton("✅ Submit Inquiry", callback_data="user_contact_submit")],
        [InlineKeyboardButton("❌ Cancel", callback_data="start_main")]
    ]
    
    await update.message.reply_text(
        f"<b>Message Buffered</b>\n\n{context.user_data['support_msg']}\n\n<blockquote>You may send more details or click 'Submit' to finalize.</blockquote>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONTACT_INPUT

async def contact_submit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    problem = context.user_data.pop("support_msg", "")
    
    if not problem:
        await query.message.edit_text("⚠️ <b>Submission Failed</b>\nNo content detected in the buffer.", parse_mode="HTML")
        return ConversationHandler.END

    # Forward to admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🆘 <b>New Support Inquiry</b>\n\n<b>From:</b> @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n\n<b>Details:</b>\n{problem}",
                parse_mode="HTML"
            )
        except:
            pass

    await query.message.edit_text(
        "✅ <b>Inquiry Submitted</b>\nYour message has been transmitted to our administrative team. We will respond shortly.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Menu", callback_data="start_main")]])
    )
    return ConversationHandler.END

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This handler now only informs users to use the contact button
    if update.effective_chat.type != "private":
        return

    user = update.message.from_user
    if user.id in ADMIN_IDS:
        return

    await update.message.reply_text(
        "ℹ️ <b>Service Information</b>\n\nTo contact our support team, please use the <b>Contact Us</b> button in the main menu.",
        parse_mode="HTML"
    )
