from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import database
import time
import os
import shutil
import zipfile
import random
import string
from config import (
    ADMIN_IDS,
    POINT_SHOP_SELECT,
    POINT_QUANTITY_SELECT,
    ADMIN_POINT_MANAGE,
    ADMIN_POINT_ADD_SERVICE,
    ADMIN_POINT_SET_COST,
    ADMIN_POINT_ADD_STOCK,
    STOCK_DIR
)

# =========================
# USER SIDE: POINT SHOP
# =========================

async def point_shop_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u_data = database.users.get(str(user_id), {})
    points = u_data.get("points", 0)

    conn = database.get_db()
    services = conn.execute("SELECT id, name, cost_per_unit FROM point_services").fetchall()
    conn.close()

    text = (
        "🎁 <b>Point Shop</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Your Balance:</b> <code>{points} points</code>\n\n"
    )

    if not services:
        text += "The shop is currently empty. Please check back later!"
        keyboard = [[InlineKeyboardButton("Return", callback_data="start_main")]]
    else:
        text += "Select a service to redeem your points:"
        keyboard = []
        for s in services:
            # Check stock count
            conn = database.get_db()
            stock_count = conn.execute("SELECT COUNT(*) as count FROM point_inventory WHERE service_id = ?", (s['id'],)).fetchone()['count']
            conn.close()
            keyboard.append([InlineKeyboardButton(f"{s['name']} ({s['cost_per_unit']} pts) - Stock: {stock_count}", callback_data=f"ps_select_{s['id']}")])
        keyboard.append([InlineKeyboardButton("Return", callback_data="start_main")])

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return POINT_SHOP_SELECT

async def point_service_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = query.data.replace("ps_select_", "")
    context.user_data["ps_service_id"] = service_id

    conn = database.get_db()
    service = conn.execute("SELECT * FROM point_services WHERE id = ?", (service_id,)).fetchone()
    stock_count = conn.execute("SELECT COUNT(*) as count FROM point_inventory WHERE service_id = ?", (service_id,)).fetchone()['count']
    conn.close()

    text = (
        f"🛒 <b>Redeeming: {service['name']}</b>\n"
        f"📝 {service['description']}\n\n"
        f"💵 <b>Price:</b> <code>{service['cost_per_unit']} points / unit</code>\n"
        f"📦 <b>Available Stock:</b> <code>{stock_count} units</code>\n\n"
        "How many units would you like to redeem?"
    )

    keyboard = []
    options = [1, 5, 10, 20]
    for opt in options:
        if opt <= stock_count:
            cost = opt * service['cost_per_unit']
            keyboard.append([InlineKeyboardButton(f"{opt} Unit{'s' if opt>1 else ''} ({cost} pts)", callback_data=f"ps_qty_{opt}")])
    
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="point_shop_init")])
    await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return POINT_QUANTITY_SELECT

async def point_redeem_finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    qty = int(query.data.replace("ps_qty_", ""))
    service_id = context.user_data.get("ps_service_id")
    user_id = query.from_user.id

    conn = database.get_db()
    service = conn.execute("SELECT * FROM point_services WHERE id = ?", (service_id,)).fetchone()
    u_data = database.users.get(str(user_id), {})
    total_cost = qty * service['cost_per_unit']

    if u_data.get("points", 0) < total_cost:
        await query.message.reply_text(f"❌ <b>Insufficient Balance</b>\nYou need {total_cost} points.", parse_mode="HTML")
        conn.close()
        return await point_shop_init(update, context)

    # RANDOMIZED SELECTION: Pull random items from stock
    stock = conn.execute("SELECT id, content FROM point_inventory WHERE service_id = ? ORDER BY RANDOM() LIMIT ?", (service_id, qty)).fetchall()
    if len(stock) < qty:
        await query.message.reply_text("❌ <b>Stock Depleted</b>", parse_mode="HTML")
        conn.close()
        return await point_shop_init(update, context)

    # Begin Atomic Transaction
    try:
        conn.execute("BEGIN TRANSACTION")
        
        # 1. Deduct points
        database.users[str(user_id)]["points"] -= total_cost
        database.save_users()

        service_name_safe = service['name'].replace(" ", "_")
        service_dir = os.path.join(STOCK_DIR, service_name_safe)
        
        delivered_paths = []
        for item in stock:
            # content stores the filename
            file_path = os.path.join(service_dir, item['content'])
            if os.path.exists(file_path):
                delivered_paths.append(file_path)
            
            # Remove from DB stock
            conn.execute("DELETE FROM point_inventory WHERE id = ?", (item['id'],))
        
        conn.commit()
        logging.info(f"POINT SHOP: User {user_id} redeemed {qty}x {service['name']} for {total_cost} pts.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Redemption Transaction Failed: {str(e)}")
        await query.message.reply_text("❌ <b>Transaction Failed:</b> Please try again later.", parse_mode="HTML")
        return ConversationHandler.END
    finally:
        conn.close()

    if not delivered_paths:
        await query.message.reply_text("❌ <b>Internal Error: Files missing from stock.</b>")
        return ConversationHandler.END

    status_msg = await query.message.edit_text("⏳ <b>Generating delivery package...</b>", parse_mode="HTML")

    try:
        if qty == 1:
            # Send single file
            await query.message.reply_document(
                document=open(delivered_paths[0], "rb"),
                caption=f"✅ <b>Redemption Successful</b>\nService: <b>{service['name']}</b>\nPoints Deducted: <code>{total_cost}</code>",
                parse_mode="HTML"
            )
        else:
            # Generate ZIP
            zip_name = f"Redeem_{service_name_safe}_{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}.zip"
            zip_path = os.path.join("temp_uploads", zip_name)
            os.makedirs("temp_uploads", exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for fp in delivered_paths:
                    zipf.write(fp, os.path.basename(fp))
            
            await query.message.reply_document(
                document=open(zip_path, "rb"),
                caption=f"✅ <b>Redemption Successful</b>\nService: <b>{service['name']}</b>\nQuantity: <code>{qty}</code>\nPoints Deducted: <code>{total_cost}</code>",
                parse_mode="HTML"
            )
            # Cleanup temp zip
            if os.path.exists(zip_path): os.remove(zip_path)

        # Cleanup stock files (permanent removal as they are redeemed)
        for fp in delivered_paths:
            if os.path.exists(fp): os.remove(fp)

        await status_msg.delete()
    except Exception as e:
        await query.message.reply_text(f"❌ <b>Delivery Failed:</b> {str(e)}")

    return ConversationHandler.END

# =========================
# ADMIN SIDE: SHOP MGMT
# =========================

async def admin_point_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS: return

    conn = database.get_db()
    services = conn.execute("SELECT * FROM point_services").fetchall()
    conn.close()

    text = "⚒ <b>Point Shop Management</b>\n\n"
    keyboard = []
    
    if not services:
        text += "<i>No services configured yet.</i>"
    else:
        for s in services:
            text += f"• <b>{s['name']}</b> ({s['cost_per_unit']} pts)\n"
            keyboard.append([InlineKeyboardButton(f"⚙️ Manage {s['name']}", callback_data=f"ap_manage_{s['id']}")])
    
    keyboard.append([InlineKeyboardButton("➕ Add New Service", callback_data="ap_add_init")])
    keyboard.append([InlineKeyboardButton("Return", callback_data="admin_main")])

    markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    return ADMIN_POINT_MANAGE

async def admin_point_service_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Safely get service_id from callback or session
    if query.data.startswith("ap_manage_"):
        service_id = query.data.replace("ap_manage_", "")
        context.user_data["ap_service_id"] = service_id
    else:
        service_id = context.user_data.get("ap_service_id")

    if not service_id:
        return await admin_point_manage(update, context)

    conn = database.get_db()
    service = conn.execute("SELECT * FROM point_services WHERE id = ?", (service_id,)).fetchone()
    
    if not service:
        conn.close()
        return await admin_point_manage(update, context)

    stock_count = conn.execute("SELECT COUNT(*) as count FROM point_inventory WHERE service_id = ?", (service_id,)).fetchone()['count']
    conn.close()

    text = (
        f"⚙️ <b>Service Management: {service['name']}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💵 <b>Cost:</b> <code>{service['cost_per_unit']} points/unit</code>\n"
        f"📦 <b>Current Stock:</b> <code>{stock_count} files</code>\n"
        f"📝 <b>Description:</b> {service['description']}\n"
    )

    keyboard = [
        [InlineKeyboardButton("➕ Upload Stock (.txt files)", callback_data="ap_stock_add")],
        [InlineKeyboardButton("💰 Change Cost", callback_data="ap_cost_edit")],
        [InlineKeyboardButton("🗑 Wipe Stock", callback_data="ap_stock_wipe_confirm")],
        [InlineKeyboardButton("❌ Delete Service", callback_data="ap_delete_confirm")],
        [InlineKeyboardButton("Back", callback_data="admin_point_manage")]
    ]

    await query.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_POINT_MANAGE

async def admin_point_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "ap_add_init":
        await query.message.edit_text("📛 <b>New Service Name:</b>", parse_mode="HTML")
        return ADMIN_POINT_ADD_SERVICE
    elif data == "ap_cost_edit":
        await query.message.edit_text("💰 <b>New Point Cost:</b>", parse_mode="HTML")
        return ADMIN_POINT_SET_COST
    elif data == "ap_stock_add":
        await query.message.edit_text("📥 <b>Upload Stock</b>\n\nPlease upload one or more <b>.txt</b> files.\nEach file represents 1 unit.", parse_mode="HTML")
        return ADMIN_POINT_ADD_STOCK
    elif data == "ap_stock_wipe_confirm":
        keyboard = [[InlineKeyboardButton("✅ Wipe", callback_data="ap_stock_wipe_execute"), InlineKeyboardButton("❌ No", callback_data=f"ap_manage_{context.user_data.get('ap_service_id')}")]]
        await query.message.edit_text("⚠️ <b>Wipe all files for this service?</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_POINT_MANAGE
    elif data == "ap_stock_wipe_execute":
        service_id = context.user_data.get("ap_service_id")
        conn = database.get_db()
        service = conn.execute("SELECT name FROM point_services WHERE id = ?", (service_id,)).fetchone()
        conn.execute("DELETE FROM point_inventory WHERE service_id = ?", (service_id,))
        conn.commit(); conn.close()
        s_dir = os.path.join(STOCK_DIR, service['name'].replace(" ", "_"))
        if os.path.exists(s_dir): shutil.rmtree(s_dir)
        return await admin_point_service_detail(update, context)
    elif data == "ap_delete_confirm":
        keyboard = [[InlineKeyboardButton("✅ Delete", callback_data="ap_delete_execute"), InlineKeyboardButton("❌ No", callback_data=f"ap_manage_{context.user_data.get('ap_service_id')}")]]
        await query.message.edit_text("⚠️ <b>Delete service and all files?</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_POINT_MANAGE
    elif data == "ap_delete_execute":
        service_id = context.user_data.get("ap_service_id")
        conn = database.get_db()
        service = conn.execute("SELECT name FROM point_services WHERE id = ?", (service_id,)).fetchone()
        conn.execute("DELETE FROM point_services WHERE id = ?", (service_id,))
        conn.commit(); conn.close()
        s_dir = os.path.join(STOCK_DIR, service['name'].replace(" ", "_"))
        if os.path.exists(s_dir): shutil.rmtree(s_dir)
        return await admin_point_manage(update, context)

async def admin_point_add_service_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    conn = database.get_db()
    try:
        conn.execute("INSERT INTO point_services (name, cost_per_unit, description) VALUES (?, ?, ?)", (name, 10, "No description set."))
        conn.commit()
        os.makedirs(os.path.join(STOCK_DIR, name.replace(" ", "_")), exist_ok=True)
        await update.message.reply_text(f"✅ Service <b>{name}</b> created.", parse_mode="HTML")
    except:
        await update.message.reply_text("❌ Already exists.")
    conn.close()
    return await admin_point_manage(update, context)

async def admin_point_set_cost_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit(): return ADMIN_POINT_SET_COST
    cost = int(update.message.text)
    service_id = context.user_data.get("ap_service_id")
    conn = database.get_db()
    conn.execute("UPDATE point_services SET cost_per_unit = ? WHERE id = ?", (cost, service_id))
    conn.commit(); conn.close()
    await update.message.reply_text("✅ Cost updated.")
    return await admin_point_manage(update, context)

async def admin_point_add_stock_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document: return ADMIN_POINT_ADD_STOCK
    service_id = context.user_data.get("ap_service_id")
    
    conn = database.get_db()
    service = conn.execute("SELECT name FROM point_services WHERE id = ?", (service_id,)).fetchone()
    service_name_safe = service['name'].replace(" ", "_")
    target_dir = os.path.join(STOCK_DIR, service_name_safe)
    os.makedirs(target_dir, exist_ok=True)

    file = await update.message.document.get_file()
    # Ensure unique filename to avoid overwrites
    orig_name = update.message.document.file_name or f"stock_{int(time.time())}.txt"
    unique_name = f"{int(time.time())}_{''.join(random.choices(string.ascii_lowercase, k=4))}_{orig_name}"
    
    await file.download_to_drive(os.path.join(target_dir, unique_name))
    
    conn.execute("INSERT INTO point_inventory (service_id, content, added_at) VALUES (?, ?, ?)", (service_id, unique_name, time.time()))
    conn.commit(); conn.close()
    
    await update.message.reply_text(f"📥 <b>Buffered:</b> {orig_name}\nSend more or click /admin when done.", parse_mode="HTML")
    return ADMIN_POINT_ADD_STOCK
