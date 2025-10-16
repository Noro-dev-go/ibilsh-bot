from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, 
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, filters, CommandHandler
)
from datetime import datetime


from integrations.gsheets_fleet_matrix import (
    create_client_column_auto,
    set_cost_value,
    upload_image_bytes_to_drive,
    place_client_photos,
)


from database.clients import add_client
from database.scooters import add_scooter, set_sheet_col_for_scooter
from database.payments import create_payment_schedule
from database.users import add_user, set_user_has_scooter
from database.pending import delete_pending_user, get_all_pending_users

from utils.schedule_utils import get_next_fridays
from utils.encryption import encrypt_file_id, decrypt_file_id


from handlers.cancel_handler import universal_cancel_handler
from handlers.admin_auth import admin_entry
from handlers.gs_sync import gs_choice_cb, gs_enter_col, GS_WAIT_COL




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
    
    encrypted_client_photo_id = encrypt_file_id(update.message.photo[-1].file_id)
    context.user_data["client_photo_id"] = encrypted_client_photo_id
    
    msg = await update.message.reply_text("📄 Пришлите фото паспорта — главная страница:")
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
    return ASK_PASSPORT_MAIN


async def receive_passport_main(update, context):
    await cleanup_register_messages(update, context)

    # Шифруем file_id перед сохранением
    encrypted_main_id = encrypt_file_id(update.message.photo[-1].file_id)
    context.user_data["passport_main_id"] = encrypted_main_id
    msg = await update.message.reply_text(
        "🏠 Пришлите фото паспорта — страница с адресом регистрации:"
    )
    context.user_data.setdefault("reg_message_ids", []).append(msg.message_id)
    return ASK_PASSPORT_ADDRESS

async def receive_passport_address(update, context):
    await cleanup_register_messages(update, context)

    # Шифруем file_id и сохраняем в user_data
    encrypted_address_id = encrypt_file_id(update.message.photo[-1].file_id)
    context.user_data["passport_address_id"] = encrypted_address_id
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

    # --- username c @ ---
    username = context.user_data.get("username")
    if not username:
        u = update.effective_user
        if u and u.username:
            username = u.username
    if username and not username.startswith("@"):
        username = f"@{username}"

    # --- 1) создаём клиента ---
    client_id = add_client(
        telegram_id=tg_id,
        username=username,
        full_name=context.user_data["full_name"],
        age=int(context.user_data["age"]),
        city=context.user_data["city"],
        phone=context.user_data["phone"],
        workplace=context.user_data.get("workplace"),
        client_photo_id=context.user_data.get("client_photo_id"),
        passport_main_id=context.user_data.get("passport_main_id"),
        passport_address_id=context.user_data.get("passport_address_id"),
    )

    # --- 2) обрабатываем каждый скутер пользователя ---
    for scooter in context.user_data.get("scooters", []):
        # 2.1) запись скутера в БД
        scooter_id = add_scooter(client_id, scooter)

        # 2.2) график платежей в БД
        weeks = scooter.get("buyout_weeks") or 10
        payment_dates = get_next_fridays(scooter["issue_date"], weeks=weeks)
        create_payment_schedule(scooter_id, payment_dates, scooter["weekly_price"])

        # 2.3) колонка в Google Sheets (левая колонка пары = даты)
        new_sheet_payload = {
            "ФИО": context.user_data["full_name"],
            "Модель": scooter.get("model", ""),
            "Дата выдачи": scooter.get("issue_date"),
            "Тег в тг": username or "",
            "Номер тел.": context.user_data["phone"],
            "Основной склад": scooter.get("warehouse", "") or "",
            "Договор": bool(scooter.get("has_contract", False)),
            "Заметки": context.user_data.get("notes", "") or "",
            "Стоимость": int(scooter.get("weekly_price", 0) or 0),
            "Зашло": 0,
        }

        left_col, _ = create_client_column_auto(new_sheet_payload, project_name="Самокат")
        set_cost_value(left_col, int(scooter.get("weekly_price", 0) or 0))
        set_sheet_col_for_scooter(scooter_id, left_col)

        # 2.4) фото → Drive → вставка в таблицу (если фотки есть)
        async def _dl(enc_file_id: str | None) -> bytes | None:
            if not enc_file_id:
                return None
            try:
                file_id = decrypt_file_id(enc_file_id)
                f = await context.bot.get_file(file_id)
                return await f.download_as_bytearray()
            except Exception as e:
                print("[PH] download from TG failed:", e)
            return None

        
        try:
            img1 = await _dl(context.user_data.get("client_photo_id"))
            img2 = await _dl(context.user_data.get("passport_main_id"))
            img3 = await _dl(context.user_data.get("passport_address_id"))

            print ("[PH] bytes present:", bool(img1), bool(img2), bool(img3))
            if not (img1 and img2 and img3):
                await update.effective_chat.send_message("⚠️ Не удалось скачать одно из фото из Telegram. Фото в Google Sheets не загружены.")
            else:
                url1 = upload_image_bytes_to_drive(img1, f"client_{scooter_id}_1.jpg")
                url2 = upload_image_bytes_to_drive(img2, f"client_{scooter_id}_2.jpg")
                url3 = upload_image_bytes_to_drive(img3, f"client_{scooter_id}_3.jpg")
                print("[PH] urls:", url1, url2, url3)
                place_client_photos(left_col, url1, url2, url3)
                print ("[PH] placed at col", left_col)
        except Exception as e:
            print ("[PH] ERROR:", e)
            await update.effective_chat.send_message("⚠️ Ошибка при загрузке фото в Google Sheets.")
            #raise
                


    # --- 3) учёт пользователя и финал ---
    add_user(
        tg_id=tg_id,
        username=username,
        full_name=context.user_data["full_name"],
        phone=context.user_data["phone"],
    )
    set_user_has_scooter(tg_id)
    delete_pending_user(tg_id)

    await update.effective_chat.send_message(
        "✅ Клиент успешно оформлен. Колонки и даты созданы в Google Sheets, стоимость выставлена."
    )
    return ConversationHandler.END





def register_admin_reg_handlers(app):
    app.add_handler(CallbackQueryHandler(handle_reg_back, pattern="^reg_back$"))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(gs_choice_cb, pattern=r"^gs_(add|skip):\d+$")],
        states={
            GS_WAIT_COL: [MessageHandler(filters.TEXT & ~filters.COMMAND, gs_enter_col)],
        },
        fallbacks=[],
        name="gsheets_add",
        persistent=False,
    ))

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
