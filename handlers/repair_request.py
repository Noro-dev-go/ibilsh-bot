from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CommandHandler, CallbackQueryHandler

from services.notifier import notify_admin_about_new_repair as send_repair_request

from handlers.cancel_handler import universal_cancel_handler
from handlers.register_client import cleanup_previous_messages

from database.repairs import save_pending_repair
from database.clients import get_client_by_tg_id
from database.scooters import get_scooters_by_client

from utils.validators import is_valid_name


from database.db import get_connection


ASK_NAME, ASK_CITY, ASK_PHONE, ASK_VIN, ASK_PROBLEM, ASK_PHOTO = range(6)
SHORT_REPAIR_DESCRIPTION, SHORT_REPAIR_PHOTO = range(100, 102)



cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|/cancel|/start|/menu|/admin)$"),
    universal_cancel_handler
)


async def cleanup_repair_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "repair_message_ids" in context.user_data:
        for msg_id in context.user_data["repair_message_ids"]:
            try:
                await update.effective_chat.delete_message(msg_id)
            except:
                pass
        context.user_data["repair_message_ids"] = []
    else:
        context.user_data["repair_message_ids"] = []



def already_pending_repair(tg_id: int) -> bool:

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM pending_repairs
                WHERE tg_id = %s AND is_processed = FALSE
            """, (tg_id,))
            return cur.fetchone() is not None



async def repair_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    tg_id = user.id
    username = user.username or "пользователь"
    message = update.message or update.callback_query.message
    context.user_data["start_message_id"] = message.message_id
    await cleanup_previous_messages(update, context)
    await cleanup_repair_messages(update, context)

    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT has_scooter FROM users WHERE tg_id = %s", (tg_id,))
            result = cur.fetchone()

    if result and result[0]:
        text = f"Привет, @{username}! У тебя что-то сломалось?"
        keyboard = [
            [InlineKeyboardButton("📝 Заполнить анкету", callback_data="short_repair")],
            [InlineKeyboardButton("🔙 Вернуться назад", callback_data="admin_to_main")]
        ]
    else:
        text = "Привет! Мы не знакомы. Если у тебя что-то сломалось, заполни анкету ниже:"
        keyboard = [
            [InlineKeyboardButton("📝 Заполнить анкету", callback_data="full_repair")],
            [InlineKeyboardButton("🔙 Вернуться назад", callback_data="admin_to_main")]
        ]

    message = update.message or update.callback_query.message
    msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["repair_message_ids"] = [msg.message_id]
  



async def start_full_repair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)  # 🧼 очистка перед началом
    await update.callback_query.answer()
    tg_id = update.effective_user.id

    if already_pending_repair(tg_id):
        keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_to_main")]
    ])
        msg = await update.callback_query.message.reply_text(
            "⚠️ У вас уже есть необработанная заявка на ремонт.\n"
            "Пожалуйста, дождитесь ответа мастера, он напишет вам в личные сообщение telegram.",
            reply_markup=keyboard
        )
        context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
        return ConversationHandler.END

    msg = await update.callback_query.message.reply_text("🧾 Введите ваше имя:")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    name = update.message.text.strip()
    if not is_valid_name(name):
        msg = await update.message.reply_text("❗ Введите корректное имя (только буквы, минимум 2 символа, без мата).")
        context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
        return ASK_NAME

    context.user_data["name"] = name
    msg = await update.message.reply_text("🏙️ Укажите ваш город:")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
    return ASK_CITY

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    context.user_data["city"] = update.message.text.strip()
    msg = await update.message.reply_text("📞 Укажите ваш номер телефона:")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 11:
        msg = await update.message.reply_text("❗ Введите корректный номер из 11 цифр:")
        context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
        return ASK_PHONE
    context.user_data["phone"] = phone
    msg = await update.message.reply_text("🛵 Введите название скутера или VIN номер:")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
    return ASK_VIN

async def ask_vin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    context.user_data["vin"] = update.message.text.strip()
    msg = await update.message.reply_text("📋 Опишите проблему:")
    context.user_data.setdefault("repair_messade_ids", []).append(msg.message_id)
    return ASK_PROBLEM

async def ask_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    context.user_data["problem"] = update.message.text.strip()
    msg = await update.message.reply_text("📸 Пришлите фото поломки (или нажмите /skip, если фото нет):")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
    return ASK_PHOTO

async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    photo = update.message.photo[-1]  
    context.user_data["photo_file_id"] = photo.file_id
    context.user_data.setdefault("repair_message_ids", []).append(update.message.message_id)
    return await finish(update, context)

async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    context.user_data["photo_file_id"] = None
    return await finish(update, context)

async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data["username"] = f"{user.username}" if user.username else "не указан"
    context.user_data["tg_id"] = user.id

    save_pending_repair(context.user_data)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_to_main")]
    ])
    await update.message.reply_text("✅ Заявка на ремонт отправлена! Ожидайте звонка мастера.", reply_markup=keyboard)
    
    await send_repair_request(context.user_data)


    return ConversationHandler.END

repair_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^Необходим ремонт$"), repair_entry),
        CallbackQueryHandler(start_full_repair, pattern="^full_repair$")  
    ],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],   
        ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        ASK_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_vin)],
        ASK_PROBLEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_problem)],  
        ASK_PHOTO: [
        MessageHandler(filters.PHOTO, receive_photo),
        CommandHandler("skip", skip_photo)
    ],
}
,
    fallbacks=[cancel_fallback]

)

# === Короткий сценарий для арендаторов ===

async def start_short_repair(update, context):
    await cleanup_repair_messages(update, context)
    await update.callback_query.answer()
    tg_id = update.effective_user.id

    if already_pending_repair(tg_id):
        keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_to_main")]
    ])
        msg = await update.callback_query.message.reply_text(
            "⚠️ У Вас уже есть активная заявка на ремонт.\n"
            "Мастер свяжется с вами в личном сообщении в telegram.",
            reply_markup=keyboard  
        )
        context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)
        return ConversationHandler.END

    msg = await update.callback_query.message.reply_text("📝 Опиши проблему со скутером:")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id) 
    return SHORT_REPAIR_DESCRIPTION

async def receive_short_description(update, context):
    await cleanup_repair_messages(update, context)
    context.user_data["repair_description"] = update.message.text
    msg = await update.message.reply_text("📸 Пришлите фото поломки:")
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id) 
    return SHORT_REPAIR_PHOTO

async def receive_short_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_repair_messages(update, context)
    user = update.effective_user
    tg_id = user.id
    username = f"{user.username}" if user.username else "не указан"

    # Сохраняем базовые поля
    context.user_data["is_short"] = True
    context.user_data["photo_file_id"] = update.message.photo[-1].file_id
    context.user_data["tg_id"] = tg_id
    context.user_data["repair_description"] = context.user_data.get("repair_description", "")
    context.user_data["problem"] = context.user_data["repair_description"]

    # Пробуем получить клиента из базы
    client = get_client_by_tg_id(tg_id)
    scooters = get_scooters_by_client(client["id"])

    vin = scooters[0]["vin"] if scooters else "-"   

    if client:
        context.user_data["name"] = client["full_name"]
        context.user_data["city"] = client["city"]
        context.user_data["phone"] = client["phone"]
        context.user_data["vin"] = vin
        context.user_data["username"] = f"{client['username']}" if client.get("username") else username
    else:
        # fallback, если почему-то клиента нет в базе
        context.user_data.setdefault("name", "арендатор Ibilsh")
        context.user_data.setdefault("city", "-")
        context.user_data.setdefault("phone", "-")
        context.user_data.setdefault("vin", "-")
        context.user_data.setdefault("username", username)

    # Сохраняем заявку и уведомляем админа
    save_pending_repair(context.user_data)
    await send_repair_request(context.user_data)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_to_main")]
    ])
    msg = await update.message.reply_text("✅ Заявка отправлена! Ожидай ответа.", reply_markup=keyboard)
    context.user_data.setdefault("repair_message_ids", []).append(msg.message_id)

    return ConversationHandler.END



short_repair_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_short_repair, pattern="^short_repair$")],
    states={
        SHORT_REPAIR_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_short_description)],
        SHORT_REPAIR_PHOTO: [MessageHandler(filters.PHOTO, receive_short_photo)],
    },
    fallbacks=[cancel_fallback],
)


repair_entry_handler = CallbackQueryHandler(repair_entry, pattern="^repair$")
repair_back_handler = CallbackQueryHandler(lambda u, c: u.callback_query.message.delete(), pattern="^repair_back$")