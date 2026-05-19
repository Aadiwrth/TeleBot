import logging
import time
import asyncio
import uvicorn
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

import database
# from api import app as fastapi_app
from config import (
    TOKEN, 
    ADMIN_IDS, 
    EDIT_INPUT, 
    GEN_TYPE,
    GEN_PARAMS,
    GEN_CONTENT_STEP,
    REDEEM_INPUT, 
    DELETE_INPUT, 
    UPLOAD_ASSETS, 
    UPLOAD_KEY_TARGET, 
    CONTACT_INPUT,
    SHORTEN_INPUT,
    PROOF_INPUT,
    SEARCH_INPUT,
    REPLY_INPUT,
    ORDER_INPUT,
    POINT_SHOP_SELECT,
    POINT_QUANTITY_SELECT,
    ADMIN_POINT_MANAGE,
    ADMIN_POINT_ADD_SERVICE,
    ADMIN_POINT_SET_COST,
    ADMIN_POINT_ADD_STOCK
)
from handlers.common import start, cancel, button_handler
from handlers.admin import (
    admin_help,
    admin_callback_handler,
    edit_select_callback,
    edit_input_handler,
    gen_params_handler,
    gen_content_step_handler,
    delete_input_handler,
    asset_upload_handler,
    asset_key_target_handler,
    shorten_input_handler,
    search_input_handler,
    admin_reply_init,
    admin_reply_handler,
    handle_smart_upload,
    cancel_edit,
    broadcast,
    stats,
    handle_admin_reply,
    admin_set_points
)
from handlers.user import (
    handle_user_message, 
    redeem_init, 
    redeem_input_handler,
    redeem_command_handler,
    proof_input_handler,
    contact_init,
    contact_input_handler,
    contact_submit_handler,
    order_init,
    order_input_handler
)
from handlers.shop import (
    point_shop_init,
    point_service_select,
    point_redeem_finalize,
    admin_point_manage,
    admin_point_service_detail,
    admin_point_callback_handler,
    admin_point_add_service_input,
    admin_point_set_cost_input,
    admin_point_add_stock_input
)

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# =========================
# ERROR HANDLING
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    
    error_message = (
        f"⚠️ <b>System Exception Detected</b>\n\n"
        f"<b>Error:</b> <code>{str(context.error)[:200]}</code>"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=error_message, parse_mode="HTML")
        except: pass

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ <b>Service Interruption</b>\nAn unexpected internal error occurred. Our administrative team has been notified.",
                parse_mode="HTML"
            )
        except: pass

# =========================
# BACKGROUND JOBS
# =========================
async def auto_prune_job(context: ContextTypes.DEFAULT_TYPE):
    """Background task to clean up expired or exhausted license keys."""
    current_time = time.time()
    to_delete = [
        c for c, d in database.codes.items() 
        if (d.get("expiry") and current_time > d["expiry"]) or 
           len(d.get("redeemed_by", [])) >= d.get("limit", 1)
    ]
    
    if not to_delete:
        return

    for code in to_delete:
        database.delete_code_assets(code)
            
    logging.info(f"Auto-Prune Task: Successfully removed {len(to_delete)} keys.")

async def main():
    # Initialize data
    database.load_data()

    bot_app = Application.builder().token(TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).pool_timeout(60).build()

    # Register error handler
    bot_app.add_error_handler(error_handler)

    # Schedule background maintenance
    if bot_app.job_queue:
        bot_app.job_queue.run_repeating(auto_prune_job, interval=86400, first=60)

    # Admin Conversation Handler
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_select_callback, pattern="^edit_select_"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_gen_init$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_db_delete_init$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_db_search_init$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_reply_init_"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_upload_init$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_shorten_init$")
        ],
        states={
            EDIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_input_handler)],
            GEN_TYPE: [CallbackQueryHandler(admin_callback_handler, pattern="^admin_gen_type_")],
            GEN_PARAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, gen_params_handler)],
            GEN_CONTENT_STEP: [
                MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.TEXT & ~filters.COMMAND, gen_content_step_handler),
                CallbackQueryHandler(admin_callback_handler, pattern="^admin_gen_step_next$")
            ],
            DELETE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_input_handler)],
            SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_handler)],
            REPLY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reply_handler)],
            UPLOAD_ASSETS: [
                MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO, asset_upload_handler),
                CallbackQueryHandler(admin_callback_handler, pattern="^admin_upload_specify$")
            ],
            UPLOAD_KEY_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, asset_key_target_handler)],
            SHORTEN_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, shorten_input_handler)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_edit, pattern="^admin_main$"),
            CommandHandler("cancel", cancel)
        ],
        per_message=False,
        allow_reentry=True
    )

    # User Conversation Handler
    user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(redeem_init, pattern="^user_redeem_init$"),
            CallbackQueryHandler(contact_init, pattern="^user_contact_init$"),
            CallbackQueryHandler(order_init, pattern="^order$")
        ],
        states={
            REDEEM_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_input_handler)],
            PROOF_INPUT: [MessageHandler(filters.PHOTO, proof_input_handler)],
            CONTACT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact_input_handler),
                CallbackQueryHandler(contact_submit_handler, pattern="^user_contact_submit$")
            ],
            ORDER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_input_handler)],
        },
        fallbacks=[
            CallbackQueryHandler(start, pattern="^start_main$"),
            CommandHandler("cancel", cancel)
        ],
        per_message=False,
        allow_reentry=True
    )

    # User Point Shop Conversation
    user_shop_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(point_shop_init, pattern="^point_shop_init$")],
        states={
            POINT_SHOP_SELECT: [CallbackQueryHandler(point_service_select, pattern="^ps_select_")],
            POINT_QUANTITY_SELECT: [CallbackQueryHandler(point_redeem_finalize, pattern="^ps_qty_")],
        },
        fallbacks=[
            CallbackQueryHandler(point_shop_init, pattern="^point_shop_init$"),
            CallbackQueryHandler(start, pattern="^start_main$")
        ],
        per_message=False,
        allow_reentry=True
    )

    # Admin Point Shop Conversation
    admin_shop_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_point_manage, pattern="^admin_point_manage$")],
        states={
            ADMIN_POINT_MANAGE: [
                CallbackQueryHandler(admin_point_service_detail, pattern="^ap_manage_"),
                CallbackQueryHandler(admin_point_callback_handler, pattern="^ap_")
            ],
            ADMIN_POINT_ADD_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_point_add_service_input)],
            ADMIN_POINT_SET_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_point_set_cost_input)],
            ADMIN_POINT_ADD_STOCK: [MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, admin_point_add_stock_input)],
        },
        fallbacks=[
            CallbackQueryHandler(admin_point_manage, pattern="^admin_point_manage$"),
            CallbackQueryHandler(admin_help, pattern="^admin_main$")
        ],
        per_message=False,
        allow_reentry=True
    )

    bot_app.add_handler(admin_conv)
    bot_app.add_handler(user_conv)
    bot_app.add_handler(user_shop_conv)
    bot_app.add_handler(admin_shop_conv)
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("redeem", redeem_command_handler))
    bot_app.add_handler(CommandHandler("cancel", cancel))
    bot_app.add_handler(CommandHandler("broadcast", broadcast))
    bot_app.add_handler(CommandHandler("stats", stats))
    bot_app.add_handler(CommandHandler("setpoints", admin_set_points))
    bot_app.add_handler(CommandHandler("admin", admin_help))

    bot_app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    bot_app.add_handler(CallbackQueryHandler(button_handler))

    bot_app.add_handler(
        MessageHandler(
            (filters.Document.ALL | filters.PHOTO | filters.VIDEO) & filters.User(set(ADMIN_IDS)) & filters.CAPTION,
            handle_smart_upload
        )
    )

    bot_app.add_handler(
        MessageHandler(
            filters.REPLY & filters.User(set(ADMIN_IDS)),
            handle_admin_reply
        )
    )

    bot_app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.REPLY,
            handle_user_message
        )
    )

    # Combined Runner
    async def run_bot():
        await bot_app.initialize()
        await bot_app.updater.start_polling()
        await bot_app.start()
        print("Bot running...")
        while True:
            await asyncio.sleep(1)
#=================Future Todo = Create a function fucking api================
    # async def run_api():
    #     config_uv = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="info")
    #     server = uvicorn.Server(config_uv)
    #     print("API running on port 8000...")
    #     await server.serve()

    # await asyncio.gather(run_bot(), run_api())
    await asyncio.gather(run_bot()) #we were going to be doing some api but in future

if __name__ == "__main__":
    asyncio.run(main())
