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
    
    # Initialize user and handle referral
    uid_str = str(user.id)
    is_new = uid_str not in database.users
    u_data = database.initialize_user(user.id, username)

    if is_new and not update.callback_query and context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            ref_id = arg.replace("ref_", "")
            if ref_id.isdigit() and ref_id != uid_str and ref_id in database.users:
                # Valid referral
                database.users[uid_str]["referred_by"] = int(ref_id)
                database.update_user(uid_str, referred_by=int(ref_id))
                
                # Update referrer
                old_ref_count = database.users[ref_id].get("referrals", 0)
                old_points = database.users[ref_id].get("points", 0)
                database.update_user(ref_id, referrals=old_ref_count + 1, points=old_points + 10)
                
                try:
                    await context.bot.send_message(
                        int(ref_id), 
                        f"🎊 <b>Referral Success</b>\nA new user has joined via your link. 10 points added to your balance.", 
                        parse_mode="HTML"
                    )
                except: pass

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
        [
            InlineKeyboardButton("Redeem Access Key", callback_data="user_redeem_init"),
            InlineKeyboardButton("🎁 Point Shop", callback_data="point_shop_init")
        ],
        [InlineKeyboardButton("Place Order", callback_data="order")],
        [
            InlineKeyboardButton("Giveaway Updates", callback_data="giveaway"),
            InlineKeyboardButton("Special Offers", callback_data="offers"),
        ],
        [
            InlineKeyboardButton("👤 My Profile", callback_data="user_profile"),
            InlineKeyboardButton("Contact Us", callback_data="user_contact_init"),
        ],
        [InlineKeyboardButton("Verification Tutorial", url="https://gofile.io/d/VIGf6Z")],
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
        await start(update, context)
        return

    if query.data == "user_profile":
        u_data = database.users.get(str(user_id), {})
        points = u_data.get("points", 0)
        refs = u_data.get("referrals", 0)
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        text = (
            "👤 <b>Personal Service Profile</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"💰 <b>Referral Points:</b> <code>{points}</code>\n"
            f"👥 <b>Total Referrals:</b> <code>{refs}</code>\n\n"
            "📢 <b>Your Referral Link:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            "<blockquote>Share this link with others. You earn <b>10 points</b> for every new user who joins via your link!</blockquote>"
        )
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Return", callback_data="start_main")]]))
        return

    key = query.data

    if key == "giveaway":
        video_path = "Assets/Redeem_code.mp4"
        file_id = database.cache.get("giveaway_video_id")
        
        # Pull dynamic content from database
        base_content = database.responses.get("giveaway", "<b>Scheduled Distributions</b>\n\nPromotional distributions are currently in the planning phase.")
        caption = f"{base_content}\n\n📺 <i>Watch the video above to learn how to redeem codes.</i>"

        if file_id:
            try:
                await query.message.reply_video(video=file_id, caption=caption, parse_mode="HTML")
                return
            except:
                pass

        if os.path.exists(video_path):
            status_msg = await query.message.reply_text("⏳ <b>Uploading instructional media...</b>\n<i>Please wait, this will only happen once.</i>", parse_mode="HTML")
            try:
                msg = await query.message.reply_video(
                    video=open(video_path, "rb"),
                    caption=caption,
                    parse_mode="HTML"
                )
                database.update_cache("giveaway_video_id", msg.video.file_id)
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit_text(f"❌ <b>Upload Failed:</b> {str(e)}\n\n" + base_content, parse_mode="HTML")
        else:
            await query.message.reply_text(base_content, parse_mode="HTML")
        return

    if key in database.responses:
        await query.message.reply_text(database.responses[key], parse_mode="HTML")
