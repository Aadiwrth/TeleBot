from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database
import os
import shutil
import time
from config import ADMIN_IDS, REDEEM_INPUT, STORAGE_DIR, CONTACT_INPUT, PROOF_INPUT, ORDER_INPUT

async def order_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("Return", callback_data="start_main")]]
    
    await query.message.edit_text(
        database.responses.get("order", "<b>Order Processing</b>") + 
        "\n\n━━━━━━━━━━━━━━━━━━━━\n"
        "💬 <b>Action Required:</b> Please send the requested details in a single message now.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ORDER_INPUT

async def order_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    order_details = update.message.text

    # Forward to admins with Reply button
    for admin_id in ADMIN_IDS:
        try:
            keyboard = [[InlineKeyboardButton("💬 Reply to Order", callback_data=f"admin_reply_init_{user.id}")]]
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🛒 <b>New Sales Order</b>\n\n"
                    f"<b>From:</b> @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n\n"
                    f"<b>Order Details:</b>\n{order_details}"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass

    await update.message.reply_text(
        "✅ <b>Order Transmitted</b>\nYour request has been logged and assigned to the sales department. An administrator will contact you shortly.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Menu", callback_data="start_main")]])
    )
    return ConversationHandler.END

async def redeem_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📖 Verification Tutorial", url="https://gofile.io/d/VIGf6Z")],
        [InlineKeyboardButton("Return", callback_data="start_main")]
    ]
    
    await query.message.edit_text(
        "<b>License Redemption Portal</b>\n\nPlease provide your unique license key to initiate the retrieval process.\n\n"
        "<i>If you are unsure how to verify the shortener link, click the tutorial button below.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REDEEM_INPUT

async def process_redemption(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """Core logic to handle key redemption."""
    user_id = update.effective_user.id
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

    # 5. Handle Text-based delivery
    if data.get("type") == "text":
        content = data.get("content", "<i>No content available for this key.</i>")
        await update.message.reply_text(
            f"<b>Redeemed Successfully</b>\n\n{content}\n\n"
            f"License Key: <code>{code}</code>\n"
            f"Status: {current_redeems + 1}/{limit} Uses Utilized",
            parse_mode="HTML"
        )
        return await finalize_redemption(update, context, code, user_id, limit)

    # 6. Asset-based delivery
    folder_path = os.path.join(STORAGE_DIR, code)
    zip_path = os.path.join(STORAGE_DIR, f"{code}.zip")

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
                "<b>Redeemed Successful</b>\n\n"
                f"License Key: <code>{code}</code>\n"
                f"Status: {current_redeems + 1}/{limit} Uses Utilized\n"
                f"Expiry: {time.ctime(data['expiry'])}"
            ),
            parse_mode="HTML"
        )
        return await finalize_redemption(update, context, code, user_id, limit)
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Delivery Failure</b>\nAn internal error occurred: {str(e)}", parse_mode="HTML")
        return ConversationHandler.END

async def redeem_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    return await process_redemption(update, context, code)

async def redeem_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /redeem {code} directly."""
    if not context.args:
        await update.message.reply_text("⚠️ <b>Usage</b>\nPlease provide a license key: <code>/redeem [KEY]</code>", parse_mode="HTML")
        return
    
    code = context.args[0].strip().upper()
    # We use a custom state for /redeem to ensure the conversation handler tracks the proof step
    # However, since this is a command, we might need to initiate the conversation or handle it standalone.
    # To keep it simple and consistent with the proof flow, we manually return the PROOF_INPUT state
    # BUT commands outside ConversationHandler don't support returning states easily.
    # BEST APPROACH: Reuse process_redemption and ensure it transitions into the PROOF state by starting the conversation.
    return await process_redemption(update, context, code)

async def finalize_redemption(update, context, code, user_id, limit):
    """Common logic after asset or text delivery."""
    # Mark as redeemed by this user
    if "redeemed_by" not in database.codes[code]:
        database.codes[code]["redeemed_by"] = []
    
    database.codes[code]["redeemed_by"].append(user_id)
    database.codes[code]["used"] = len(database.codes[code]["redeemed_by"]) >= limit
    
    # Update user metadata
    user = update.message.from_user
    username = f"@{user.username}" if user.username else user.first_name
    database.initialize_user(user.id, username)
    
    database.save_codes()
    # database.save_users() is already called inside initialize_user

    # Store code for proof association
    context.user_data["active_redeem_code"] = code

    # Transition to Proof Submission
    await update.message.reply_text(
        "📸 <b>Submission Required</b>\n\nTo maintain service integrity, please send a <b>Screenshot</b> of your successful login/redemption as proof.\n\n"
        "<i>Only image files (PNG, JPG) are accepted.</i>",
        parse_mode="HTML"
    )
    return PROOF_INPUT

async def proof_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = context.user_data.get("active_redeem_code", "UNKNOWN")
    
    if not update.message.photo:
        await update.message.reply_text("⚠️ <b>Invalid Format</b>\nPlease send an actual <b>Image/Screenshot</b> as proof. Documents and text are not permitted here.", parse_mode="HTML")
        return PROOF_INPUT

    # Forward the proof to all admins with verification buttons
    for admin_id in ADMIN_IDS:
        try:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"admin_proof_approve_{user.id}_{code}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"admin_proof_reject_{user.id}_{code}")
                ]
            ]
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=update.message.photo[-1].file_id,
                caption=(
                    f"📸 <b>New Redemption Proof</b>\n\n"
                    f"<b>From:</b> @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n"
                    f"<b>Key:</b> <code>{code}</code>\n\n"
                    f"<blockquote>Please verify the screenshot and take action below.</blockquote>"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass

    await update.message.reply_text(
        "✅ <b>Proof Received</b>\nThank you for your cooperation. Your submission has been logged by the administrative team. You will be notified once reviewed.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return to Menu", callback_data="start_main")]])
    )
    return ConversationHandler.END

# =========================
# CONTACT / SUPPORT SYSTEM
# =========================

async def contact_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["support_msg"] = ""
    
    await query.message.edit_text(
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
            keyboard = [[InlineKeyboardButton("💬 Reply", callback_data=f"admin_reply_init_{user.id}")]]
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🆘 <b>New Support Inquiry</b>\n\n<b>From:</b> @{user.username or user.first_name} (ID: <code>{user.id}</code>)\n\n<b>Details:</b>\n{problem}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
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
    if update.effective_chat.type != "private":
        return

    user = update.message.from_user
    if user.id in ADMIN_IDS:
        return

    await update.message.reply_text(
        "ℹ️ <b>Service Information</b>\n\nTo contact our support team, please use the <b>Contact Us</b> button in the main menu.",
        parse_mode="HTML"
    )
