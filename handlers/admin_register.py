from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, 
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters, CommandHandler
)
from datetime import datetime



from database.clients import add_client
from database.scooters import add_scooter
from database.payments import create_payment_schedule
from database.users import add_user, set_user_has_scooter
from database.pending import delete_pending_user, get_all_pending_users

from utils.schedule_utils import get_next_fridays

from handlers.cancel_handler import universal_cancel_handler
from handlers.admin_auth import admin_entry




# Состояния FSM
(
    ASK_FULLNAME, ASK_AGE, ASK_CITY, ASK_PHONE, ASK_WORKPLACE, 
    ASK_CLIENT_PHOTO, ASK_PASSPORT_MAIN, ASK_PASSPORT_ADDRESS, 
    ASK_SCOOTER_COUNT, SCOOTER_MODEL, SCOOTER_VIN, SCOOTER_MOTOR_VIN, 
    SCOOTER_ISSUE_DATE, SCOOTER_TARIFF, SCOOTER_BUYOUT, SCOOTER_PRICE, 
    SCOOTER_OPTIONS_CONTINUE
) = range(17)

# Флаги по скутеру
OPTIONS = [
    ("has_contract", "📄 Договор оформлен?"),
    ("has_second_keys", "🔑 Вторые ключи?"),
    ("has_tracker", "📡 Датчик отслеживания?"),
    ("has_limiter", "🛑 Ограничитель скорости?"),
    ("has_pedals", "🚲 Педали установлены?"),
    ("has_sim", "📶 ПЭСИМ-карта активна?")
]


cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|/cancel|/start|/menu|/admin)$"),
    universal_cancel_handler
)


async def cleanup_register_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for msg_id in context.user_data.get("reg_message_ids", []):
        try:
            await update.effective_chat.delete_message(msg_id)
        except:
            pass
    context.user_data["reg_message_ids"] = []


async def handle_reg_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    for key in ["admin_message_ids", "client_message_ids", "reg_message_ids"]:
        for msg_id in context.user_data.get(key, []):
            try:
                await update.effective_chat.delete_message(msg_id)
            except:
                pass
        context.user_data[key] = []

   
    return await admin_entry(update, context)



# Запуск анкеты

async def fill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_register_messages(update, context)  

    tg_id = int(query.data.split(":")[1])
    context.user_data["tg_id_to_register"] = tg_id

    for user in get_all_pending_users():
        if user[0] == tg_id:
            context.user_data["username"] = user[1]

    msg = await query.message.reply_text("👤 Введите полное имя клиента:", reply_markup=ReplyKeyboardRemove())
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return ASK_FULLNAME

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    context.user_data["full_name"] = update.message.text.strip()

    msg = await update.message.reply_text("Введите возраст клиента (от 18 до 65 лет):")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return ASK_AGE

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    age = update.message.text.strip()
    if not age.isdigit() or not (18 <= int(age) <= 65):
        msg = await update.message.reply_text("❗ Введите корректный возраст (18–65):")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return ASK_AGE

    context.user_data["age"] = age

    msg = await update.message.reply_text("Введите город клиента:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return ASK_CITY

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    city = update.message.text.strip()
    context.user_data["city"] = city

    msg = await update.message.reply_text("Введите номер телефона (11 цифр):")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return ASK_PHONE

async def ask_workplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 11:
        msg = await update.message.reply_text("❗ Введите корректный номер телефона (11 цифр):")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return ASK_PHONE

    context.user_data["phone"] = phone
    msg = await update.message.reply_text("Укажите место работы клиента:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return ASK_WORKPLACE

async def ask_client_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)
    context.user_data["workplace"] = update.message.text.strip()
    msg = await update.message.reply_text("📸 Пришлите фото клиента с электровелосипедом либо с аккумулятором")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
    return ASK_CLIENT_PHOTO

async def receive_client_photo(update, context):
    await cleanup_register_messages(update, context)
    context.user_data["client_photo_id"] = update.message.photo[-1].file_id
    msg = await update.message.reply_text("📄 Пришлите фото паспорта — главная страница:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
    return ASK_PASSPORT_MAIN

async def receive_passport_main(update, context):
    await cleanup_register_messages(update, context)
    context.user_data["passport_main_id"] = update.message.photo[-1].file_id
    msg = await update.message.reply_text("🏠 Пришлите фото паспорта — страница с адресом регистрации:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
    return ASK_PASSPORT_ADDRESS

async def receive_passport_address(update, context):
    await cleanup_register_messages(update, context)
    context.user_data["passport_address_id"] = update.message.photo[-1].file_id
    return await ask_scooter_count(update, context)

async def ask_scooter_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    msg = await update.message.reply_text("📦 Сколько скутеров будет оформлено на клиента? Введите число в поле ввода:\n\n" \
    "Если оформляем аренду АКБ - укажите цифру 1.")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return ASK_SCOOTER_COUNT

async def receive_scooter_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        msg = await update.message.reply_text("❗ Введите положительное число.")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return ASK_SCOOTER_COUNT

    count = int(text)
    context.user_data["scooter_count"] = count
    context.user_data["current_scooter"] = 1
    context.user_data["scooters"] = []
    context.user_data["scooter_data"] = {}

    msg1 = await update.message.reply_text(f"Заполняем скутер №{context.user_data['current_scooter']}")
    msg2 = await update.message.reply_text("Введите модель скутера:")

    context.user_data.setdefault("reg_message_ids", []).extend([msg1.message_id, msg2.message_id])

    return SCOOTER_MODEL

# Блок по каждому скутеру:

async def ask_scooter_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    context.user_data.setdefault("scooter_data", {})
    context.user_data["scooter_data"]["model"] = update.message.text.strip()

    msg = await update.message.reply_text("Введите VIN рамы либо VIN АКБ:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_VIN

async def ask_scooter_vin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    context.user_data["scooter_data"]["vin"] = update.message.text.strip()

    msg = await update.message.reply_text("Введите VIN мотора:\n\n" \
    "Если оформляем АКБ - поставьте прочерк.")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_MOTOR_VIN

async def ask_scooter_motor_vin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    context.user_data["scooter_data"]["motor_vin"] = update.message.text.strip()

    msg = await update.message.reply_text("Введите дату выдачи (ДД.ММ.ГГГГ):")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_ISSUE_DATE

async def ask_scooter_issue_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    try:
        issue_date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        msg = await update.message.reply_text("❗ Неверный формат даты.")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return SCOOTER_ISSUE_DATE

    context.user_data["scooter_data"]["issue_date"] = issue_date

    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("1 АКБ")],
        [KeyboardButton("2 АКБ")],
        [KeyboardButton("Выкуп")]
    ], resize_keyboard=True)

    msg = await update.message.reply_text("Выберите тип тарифа:", reply_markup=keyboard)
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_TARIFF

async def handle_scooter_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    tariff = update.message.text.strip()
    allowed = ["1 АКБ", "2 АКБ", "Выкуп"]
    if tariff not in allowed:
        msg = await update.message.reply_text("❗ Выберите из предложенных вариантов.")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return SCOOTER_TARIFF

    context.user_data["scooter_data"]["tariff_type"] = tariff

    if tariff == "Выкуп":
        msg = await update.message.reply_text("Введите срок выкупа в неделях:")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return SCOOTER_BUYOUT
    else:
        context.user_data["scooter_data"]["buyout_weeks"] = None
        msg = await update.message.reply_text("Введите стоимость аренды в неделю:")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return SCOOTER_PRICE

async def ask_scooter_buyout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    weeks = update.message.text.strip()
    if not weeks.isdigit():
        msg = await update.message.reply_text("❗ Введите количество недель.")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return SCOOTER_BUYOUT

    context.user_data["scooter_data"]["buyout_weeks"] = int(weeks)

    msg = await update.message.reply_text("Введите стоимость аренды в неделю:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_PRICE

async def ask_scooter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    price = update.message.text.strip()
    if not price.isdigit():
        msg = await update.message.reply_text("❗ Введите сумму.")
        context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
        return SCOOTER_PRICE

    context.user_data["scooter_data"]["weekly_price"] = int(price)
    context.user_data["option_step"] = 0

    key, label = OPTIONS[0]
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data="flag_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="flag_no")
        ]
    ])

    msg = await update.message.reply_text(label, reply_markup=keyboard)
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_OPTIONS_CONTINUE


async def handle_option_flag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_register_messages(update, context)

    answer = query.data == "flag_yes"
    step = context.user_data.get("option_step", 0)
    key, _ = OPTIONS[step]

    context.user_data["scooter_data"][key] = answer
    step += 1

    if step >= len(OPTIONS):
        return await finish_scooter_entry(update, context)

    context.user_data["option_step"] = step
    next_key, next_label = OPTIONS[step]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data="flag_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="flag_no")
        ]
    ])
    msg = await query.message.reply_text(next_label, reply_markup=keyboard)
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)

    return SCOOTER_OPTIONS_CONTINUE


async def finish_scooter_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)

    scooter = context.user_data["scooter_data"].copy()
    context.user_data["scooters"].append(scooter)

    current = context.user_data["current_scooter"]
    total = context.user_data["scooter_count"]

    if current < total:
        context.user_data["current_scooter"] += 1
        context.user_data["scooter_data"] = {}

        msg1 = await update.callback_query.message.reply_text(
            f"Переходим к скутеру №{context.user_data['current_scooter']}"
        )
        msg2 = await update.callback_query.message.reply_text("Введите модель скутера:")

        context.user_data.setdefault("reg_message_ids", []).extend([msg1.message_id, msg2.message_id])

        return SCOOTER_MODEL
    else:
        return await save_all_data(update, context)


async def save_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_register_messages(update, context)
    tg_id = context.user_data["tg_id_to_register"]
    username = context.user_data.get("username")

    client_id = add_client(
        telegram_id=tg_id,
        username=username,
        full_name=context.user_data["full_name"],
        age=int(context.user_data["age"]),
        city=context.user_data["city"],
        phone=context.user_data["phone"],
        workplace=context.user_data["workplace"],
        client_photo_id=context.user_data.get("client_photo_id"),
        passport_main_id=context.user_data.get("passport_main_id"),
        passport_address_id=context.user_data.get("passport_address_id")
    )

    for scooter in context.user_data["scooters"]:
        scooter_id = add_scooter(client_id, scooter)
        weeks = scooter.get("buyout_weeks") or 10
        payment_dates = get_next_fridays(scooter["issue_date"], weeks=weeks)
        create_payment_schedule(scooter_id, payment_dates, scooter["weekly_price"])

    add_user(
        tg_id=tg_id,
        username=username,
        full_name=context.user_data["full_name"],
        phone=context.user_data["phone"]
    )

    set_user_has_scooter(tg_id)
    delete_pending_user(tg_id)

   
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Назад в главное меню админа", callback_data="reg_back"),
        ]
    ])
    msg = await update.callback_query.message.reply_text("✅ Клиент успешно оформлен. График платежей создан.", reply_markup=keyboard)

    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)  

    return ConversationHandler.END




def register_admin_reg_handlers(app):
    app.add_handler(CallbackQueryHandler(handle_reg_back, pattern="^reg_back$"))

admin_register_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(fill_callback, pattern=r"^fill:\d+$")],
    states={
        ASK_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
        ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],
        ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_workplace)],
        ASK_WORKPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_photo)],
        ASK_CLIENT_PHOTO: [MessageHandler(filters.PHOTO, receive_client_photo)],
        ASK_PASSPORT_MAIN: [MessageHandler(filters.PHOTO, receive_passport_main)],
        ASK_PASSPORT_ADDRESS: [MessageHandler(filters.PHOTO, receive_passport_address)],
        ASK_SCOOTER_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_scooter_count)],
        SCOOTER_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_scooter_model)],
        SCOOTER_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_scooter_vin)],
        SCOOTER_MOTOR_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_scooter_motor_vin)],
        SCOOTER_ISSUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_scooter_issue_date)],
        SCOOTER_TARIFF: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_scooter_tariff)],
        SCOOTER_BUYOUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_scooter_buyout)],
        SCOOTER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_scooter_price)],
        SCOOTER_OPTIONS_CONTINUE: [CallbackQueryHandler(handle_option_flag, pattern="^flag_(yes|no)$")],
    },
    fallbacks=[cancel_fallback],
)
