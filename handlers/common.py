from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database
import os
from utils import check_force_join
import handlers.admin # For admin_help redirection

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If this was called as a callback
    if update.callback_query:
        query = update.callback_query
        user = query.from_user
        msg_obj = query.message
    else:
        user = update.message.from_user
        msg_obj = update.message

    username = f"@{user.username}" if user.username else user.first_name
    database.users[str(user.id)] = username
    database.save_users()

    missing_channels = await check_force_join(user.id, context.bot)

    if missing_channels:
        text = "🚫 <b>You must join all channels first:</b>\n\n"
        keyboard = []
        for ch in missing_channels:
            text += f"• {ch}\n"
            keyboard.append([
                InlineKeyboardButton(
                    ch.replace("@", ""),
                    url=f"https://t.me/{ch.replace('@', '')}"
                )
            ])
        keyboard.append([InlineKeyboardButton("📂 Folder Add", url="https://t.me/addlist/jxjn8TtNuSMwNTA1")])
        keyboard.append([InlineKeyboardButton("✅ Joined", callback_data="checkjoin")])

        await msg_obj.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    keyboard = [
        [
            InlineKeyboardButton("Netflix Services", callback_data="nfcookies"),
            InlineKeyboardButton("Google AI Pro", callback_data="googleaipro"),
        ],
        [InlineKeyboardButton("Redeem Access Key", callback_data="user_redeem_init")],
        [InlineKeyboardButton("Place Order", callback_data="order")],
        [
            InlineKeyboardButton("Giveaway Updates", callback_data="giveaway"),
            InlineKeyboardButton("Special Offers", callback_data="offers"),
        ],
        [
            InlineKeyboardButton("Contact Us", callback_data="user_contact_init"),
            InlineKeyboardButton("Verification Tutorial", url="https://gofile.io/d/VIGf6Z"),
        ],
    ]

    await msg_obj.reply_text(
        "<b>Service Interface Initialized</b>\n\nWelcome to the FGA automated service portal. Please select a category below for further information.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Universal cancel for commands."""
    await update.message.reply_text("🚫 <b>Operation Aborted</b>", parse_mode="HTML")
    await start(update, context)
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "checkjoin":
        missing_channels = await check_force_join(user_id, context.bot)
        if missing_channels:
            await query.message.reply_text("❌ You still haven't joined all channels.")
            return
        await query.message.reply_text("✅ Verification successful!\nUse /start again.")
        return

    if query.data == "admin_main":
        await handlers.admin.admin_help(update, context)
        return

    if query.data == "start_main":
        # Simplified start menu trigger for callbacks
        await query.message.delete()
        # Mocking update.message for start call
        query.message.from_user = query.from_user
        await start(query, context)
        return

    key = query.data

    if key in database.responses:
        await query.message.reply_text(database.responses[key], parse_mode="HTML")
