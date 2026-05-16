import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

import database
from config import (
    TOKEN, 
    ADMIN_IDS, 
    EDIT_INPUT, 
    GEN_DURATION, 
    REDEEM_INPUT, 
    DELETE_INPUT, 
    UPLOAD_ASSETS, 
    UPLOAD_KEY_TARGET, 
    CONTACT_INPUT,
    SHORTEN_INPUT,
    PROOF_INPUT
)
from handlers.common import start, cancel, button_handler
from handlers.admin import (
    admin_help,
    admin_callback_handler,
    edit_select_callback,
    edit_input_handler,
    gen_input_handler,
    delete_input_handler,
    asset_upload_handler,
    asset_key_target_handler,
    shorten_input_handler,
    cancel_edit,
    broadcast,
    stats,
    handle_admin_reply
)
from handlers.user import (
    handle_user_message, 
    redeem_init, 
    redeem_input_handler,
    proof_input_handler,
    contact_init,
    contact_input_handler,
    contact_submit_handler
)

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)

def main():
    # Initialize data
    database.load_data()

    app = Application.builder().token(TOKEN).build()

    # Admin Conversation Handler for editing responses
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_select_callback, pattern="^edit_select_"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_gen_params$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_db_delete_init$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_upload_init$"),
            CallbackQueryHandler(admin_callback_handler, pattern="^admin_shorten_init$")
        ],
        states={
            EDIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_input_handler)],
            GEN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, gen_input_handler)],
            DELETE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_input_handler)],
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

    # User Conversation Handler for redemption and contact
    user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(redeem_init, pattern="^user_redeem_init$"),
            CallbackQueryHandler(contact_init, pattern="^user_contact_init$")
        ],
        states={
            REDEEM_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_input_handler)],
            PROOF_INPUT: [MessageHandler(filters.PHOTO, proof_input_handler)],
            CONTACT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contact_input_handler),
                CallbackQueryHandler(contact_submit_handler, pattern="^user_contact_submit$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(start, pattern="^start_main$"),
            CommandHandler("cancel", cancel)
        ],
        per_message=False,
        allow_reentry=True
    )

    app.add_handler(admin_conv)
    app.add_handler(user_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("admin", admin_help))

    # All admin-specific callbacks consolidated
    app.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))

    # Common button handler
    app.add_handler(CallbackQueryHandler(button_handler))

    # Admin reply handler
    app.add_handler(
        MessageHandler(
            filters.REPLY & filters.User(set(ADMIN_IDS)),
            handle_admin_reply
        )
    )

    # User message handler (for DMs)
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.REPLY,
            handle_user_message
        )
    )

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
