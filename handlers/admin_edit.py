from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from database.clients import update_client_field
from database.scooters import get_scooter_by_id, get_scooters_by_client, update_scooter_field
from datetime import datetime

from handlers.admin_panel import handle_back_to_clients, show_single_client

from handlers.cancel_handler import universal_cancel_handler

from handlers.keyboard_utils import get_admin_inline_keyboard

# Состояния FSM
(
    CHOOSE_SECTION, CHOOSE_FIELD,
    EDIT_NAME, EDIT_AGE, EDIT_CITY, EDIT_PHONE, EDIT_WORKPLACE,
    CHOOSE_SCOOTER, CHOOSE_SCOOTER_FIELD,
    EDIT_MODEL, EDIT_VIN, EDIT_MOTOR_VIN, EDIT_DATE,
    SELECT_TARIFF_TYPE, INPUT_BUYOUT_WEEKS, INPUT_WEEKLY_PRICE, CHOOSE_FLAGS, EDIT_FLAG
) = range(18)

cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|/cancel|/start|/menu|/admin)$"),
    universal_cancel_handler
)

async def cleanup_edit_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_message_ids" in context.user_data:
        for msg_id in context.user_data["edit_message_ids"]:
            try:
                await update.effective_chat.delete_message(msg_id)
            except:
                pass
        context.user_data["edit_message_ids"] = []
    else:
        context.user_data["edit_message_ids"] = []


async def cleanup_client_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_ids = context.user_data.get("client_message_ids", [])
    for msg_id in message_ids:
        try:
            await update.effective_chat.delete_message(msg_id)
        except:
            pass
    context.user_data["client_message_ids"] = []



async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)
    await cleanup_client_messages(update, context)

    await update.callback_query.answer()
    await update.callback_query.message.edit_text("Вы в админке.", reply_markup=get_admin_inline_keyboard())  # или show_admin_panel()

    return ConversationHandler.END

# Старт редактирования клиента
async def start_edit_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Очистка интерфейса
    await cleanup_client_messages(update, context)
    await cleanup_edit_messages(update, context)
    context.user_data["edit_message_ids"] = []
    context.user_data["edit_field"] = None

    # Сохраняем ID клиента
    client_id = int(query.data.split(":")[1])
    context.user_data["edit_client_id"] = client_id
    context.user_data["client_id"] = client_id

    # Отображаем выбор типа редактирования
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001F464 Данные клиента", callback_data="edit_profile")],
        [InlineKeyboardButton("\U0001F6F5 Скутеры клиента", callback_data="edit_scooters")],
        [InlineKeyboardButton("\u2B05\uFE0F Назад к клиенту", callback_data="admin_back_client")],
    ])

    msg = await update.effective_chat.send_message(
        "Что хотите редактировать:", reply_markup=keyboard
    )
    context.user_data["edit_message_ids"].append(msg.message_id)



# === Работа с CLIENT ===

async def back_to_client_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Данные клиента", callback_data="edit_profile")],
        [InlineKeyboardButton("🛵 Скутеры клиента", callback_data="edit_scooters")],
        [InlineKeyboardButton("⬅️ Назад в к клиенту", callback_data="admin_back_client")]
    ])
    if context.user_data.get("editing_came_from_search"):  
        client_id = context.user_data.get("edit_client_id")
        await show_single_client(update, context, client_id)

        context.user_data.pop("editing_came_from_search", None)
        return ConversationHandler.END

    await query.message.reply_text("Что хотите редактировать:", reply_markup=keyboard)
    return CHOOSE_SECTION

async def choose_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    query = update.callback_query
    await query.answer()

    if query.data == "edit_profile":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ ФИО", callback_data="edit_name")],
            [InlineKeyboardButton("📅 Возраст", callback_data="edit_age")],
            [InlineKeyboardButton("📍 Город", callback_data="edit_city")],
            [InlineKeyboardButton("📞 Телефон", callback_data="edit_phone")],
            [InlineKeyboardButton("🏢 Работа", callback_data="edit_workplace")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_client_menu")]
        ])
        msg = await update.effective_chat.send_message("Выберите что редактировать:", reply_markup=keyboard)

        context.user_data["edit_message_ids"].append(msg.message_id)
        return CHOOSE_FIELD

    elif query.data == "edit_scooters":
        client_id = context.user_data["edit_client_id"]
        scooters = get_scooters_by_client(client_id)
        if not scooters:
            msg = await query.message.reply_text("❌ У клиента нет скутеров.")
            context.user_data.setdefault("edit_message_ids", []).append(msg.message_id)
            return ConversationHandler.END

        keyboard = []
        for scooter in scooters:
            button = InlineKeyboardButton(
                f"{scooter['model']} (VIN: {scooter['vin']})",
                callback_data=f"scooter_id:{scooter['id']}"
            )
            keyboard.append([button])

        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_client_menu")])
        msg = await query.message.reply_text("Выберите скутер:", reply_markup=InlineKeyboardMarkup(keyboard))

        context.user_data.setdefault("edit_message_ids", []).append(msg.message_id)
        return CHOOSE_SCOOTER

    

async def choose_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)

    query = update.callback_query
    await query.answer()
    field = query.data.split("_")[1]
    context.user_data["edit_field"] = field

    prompts = {
        "name": "Введите новое ФИО:",
        "age": "Введите новый возраст:",
        "city": "Введите новый город:",
        "phone": "Введите новый телефон:",
        "workplace": "Введите новое место работы:"
    }

    msg = await update.effective_chat.send_message(prompts[field])  
    context.user_data["edit_message_ids"].append(msg.message_id)

    state_map = {
        "name": EDIT_NAME,
        "age": EDIT_AGE,
        "city": EDIT_CITY,
        "phone": EDIT_PHONE,
        "workplace": EDIT_WORKPLACE
    }

    return state_map[field]

async def process_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    client_id = context.user_data["edit_client_id"]
    value = update.message.text.strip()
    update_client_field(client_id, "full_name", value)

    msg = await update.message.reply_text("✅ ФИО обновлено.")
    context.user_data["edit_message_ids"].append(msg.message_id)

    await back_to_field_menu(update, context)
    return CHOOSE_FIELD

async def process_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    client_id = context.user_data["edit_client_id"]
    value = update.message.text.strip()

    if not value.isdigit() or not (14 <= int(value) <= 100):
        msg = await update.message.reply_text("Введите возраст от 14 до 100.")
        context.user_data["edit_message_ids"].append(msg.message_id)
        return EDIT_AGE

    update_client_field(client_id, "age", int(value))
    msg = await update.message.reply_text("✅ Возраст обновлён.")
    context.user_data["edit_message_ids"].append(msg.message_id)

    await back_to_field_menu(update, context)
    return CHOOSE_FIELD

async def process_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[FSM] process_city: старт")

    await cleanup_edit_messages(update, context)

    client_id = context.user_data.get("edit_client_id")
    value = update.message.text.strip()
    print(f"[FSM] process_city: новое значение = {value}")

    try:
        update_client_field(client_id, "city", value)
        msg = await update.message.reply_text("✅ Город обновлён.")
        context.user_data["edit_message_ids"].append(msg.message_id)
    except Exception as e:
        print(f"[FSM] process_city: ошибка при обновлении или reply_text → {e}")
        await update.message.reply_text("❌ Ошибка при обновлении города.")
        return EDIT_CITY

    print("[FSM] process_city: возврат в back_to_field_menu")

    try:
        await back_to_field_menu(update, context)
    except Exception as e:
        print(f"[FSM] Ошибка в back_to_field_menu: {e}")
        await update.message.reply_text("❌ Ошибка при возврате в меню.")
        return ConversationHandler.END

    print("[FSM] process_city: возврат CHOOSE_FIELD")
    return CHOOSE_FIELD


async def process_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    client_id = context.user_data["edit_client_id"]
    value = update.message.text.strip()
    update_client_field(client_id, "phone", value)

    msg = await update.message.reply_text("✅ Телефон обновлён.")
    context.user_data["edit_message_ids"].append(msg.message_id)

    await back_to_field_menu(update, context)
    return CHOOSE_FIELD

async def process_workplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    client_id = context.user_data["edit_client_id"]
    value = update.message.text.strip()
    update_client_field(client_id, "workplace", value)

    msg = await update.message.reply_text("✅ Место работы обновлено.")
    context.user_data["edit_message_ids"].append(msg.message_id)

    await back_to_field_menu(update, context)
    return CHOOSE_FIELD

async def back_to_field_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ ФИО", callback_data="edit_name")],
        [InlineKeyboardButton("📅 Возраст", callback_data="edit_age")],
        [InlineKeyboardButton("📍 Город", callback_data="edit_city")],
        [InlineKeyboardButton("📞 Телефон", callback_data="edit_phone")],
        [InlineKeyboardButton("🏢 Работа", callback_data="edit_workplace")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_client_menu")]
    ])

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        msg = await query.message.edit_text("Выберите поле для редактирования:", reply_markup=keyboard)
    else:
        msg = await update.message.reply_text("Выберите поле для редактирования:", reply_markup=keyboard)

    context.user_data["edit_message_ids"].append(msg.message_id)

    return CHOOSE_FIELD

# === Работа с SCOOTER ===

async def back_to_scooters_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_edit_messages(update, context)  

    client_id = context.user_data["edit_client_id"]
    scooters = get_scooters_by_client(client_id)

    keyboard = []
    for scooter in scooters:
        button = InlineKeyboardButton(
            f"{scooter['model']} (VIN: {scooter['vin']})",
            callback_data=f"scooter_id:{scooter['id']}"
        )
        keyboard.append([button])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_client_menu")])
    msg = await query.message.reply_text("Выберите скутер:", reply_markup=InlineKeyboardMarkup(keyboard))

    context.user_data["edit_message_ids"].append(msg.message_id)  

    return CHOOSE_SCOOTER


async def choose_scooter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_edit_messages(update, context)  

    scooter_id = int(query.data.split(":")[1])
    context.user_data["selected_scooter_id"] = scooter_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛵 Модель", callback_data="field_model")],
        [InlineKeyboardButton("🔢 VIN", callback_data="field_vin")],
        [InlineKeyboardButton("⚙️ VIN мотора", callback_data="field_motor")],
        [InlineKeyboardButton("📅 Дата выдачи", callback_data="field_date")],
        [InlineKeyboardButton("💳 Тариф", callback_data="field_tariff")],
        [InlineKeyboardButton("🧩 Доп. комплектация", callback_data="field_flags")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_scooters_list")]
    ])

    msg = await query.message.reply_text("Выберите поле для редактирования:", reply_markup=keyboard)
    context.user_data["edit_message_ids"].append(msg.message_id)  

    return CHOOSE_SCOOTER_FIELD


async def choose_scooter_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_edit_messages(update, context)

    field = query.data.split("_")[1]
    context.user_data["edit_scooter_field"] = field

    if field == "flags":
        return await choose_flags(update, context)
    if field == "tariff":
        return await select_tariff_type(update, context)

    prompts = {
        "model": "Введите новую модель:",
        "vin": "Введите новый VIN:",
        "motor": "Введите новый VIN мотора:",
        "date": "Введите новую дату выдачи (ДД.ММ.ГГГГ):"
    }

    msg = await query.message.reply_text(prompts[field])
    context.user_data["edit_message_ids"].append(msg.message_id) 

    state_map = {
        "model": EDIT_MODEL,
        "vin": EDIT_VIN,
        "motor": EDIT_MOTOR_VIN,
        "date": EDIT_DATE,
    }

    return state_map[field]


async def process_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)
    scooter_id = context.user_data["selected_scooter_id"]
    value = update.message.text.strip()
    update_scooter_field(scooter_id, "model", value)
    msg = await update.message.reply_text("✅ Модель обновлена.")
    context.user_data["edit_message_ids"].append(msg.message_id) 
    return await back_to_scooter_field_menu(update, context)


async def process_vin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  
    scooter_id = context.user_data["selected_scooter_id"]
    value = update.message.text.strip()
    update_scooter_field(scooter_id, "vin", value)
    msg = await update.message.reply_text("✅ VIN обновлён.")
    context.user_data["edit_message_ids"].append(msg.message_id)
    return await back_to_scooter_field_menu(update, context)

async def process_motor_vin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context) 
    scooter_id = context.user_data["selected_scooter_id"]
    value = update.message.text.strip()
    update_scooter_field(scooter_id, "motor_vin", value)
    msg = await update.message.reply_text("✅ VIN мотора обновлён.")
    context.user_data["edit_message_ids"].append(msg.message_id)
    return await back_to_scooter_field_menu(update, context)

async def process_issue_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)
    scooter_id = context.user_data["selected_scooter_id"]
    value = update.message.text.strip()
    try:
        date_obj = datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты.")
        return EDIT_DATE
    update_scooter_field(scooter_id, "issue_date", date_obj)
    msg = await update.message.reply_text("✅ Дата обновлена.")
    context.user_data["edit_messages_ids"].append(msg.message_id)
    return await back_to_scooter_field_menu(update, context)


async def back_to_scooter_field_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Модель", callback_data="field_model")],
        [InlineKeyboardButton("🧾 VIN", callback_data="field_vin")],
        [InlineKeyboardButton("🧾 VIN мотора", callback_data="field_motor")],
        [InlineKeyboardButton("📅 Дата выдачи", callback_data="field_date")],
        [InlineKeyboardButton("📊 Тариф", callback_data="field_tariff")],
        [InlineKeyboardButton("📦 Доп. комплектация", callback_data="field_flags")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back_to_scooters_list")]
    ])

    # Универсальная проверка
    if update.callback_query:
        msg = await update.callback_query.message.reply_text(
            "Выберите поле для редактирования:", reply_markup=keyboard)
    else:
        msg = await update.message.reply_text(
            "Выберите поле для редактирования:", reply_markup=keyboard)

    context.user_data["edit_message_ids"].append(msg.message_id)
    return CHOOSE_SCOOTER_FIELD



# === TARIFF ===

async def select_tariff_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1 АКБ", callback_data="tariff_1"),
            InlineKeyboardButton("2 АКБ", callback_data="tariff_2")
        ],
        [InlineKeyboardButton("Выкуп", callback_data="tariff_buyout")]
    ])

    msg = await query.message.reply_text("Выберите тип тарифа:", reply_markup=keyboard)
    context.user_data["edit_message_ids"].append(msg.message_id)

    return SELECT_TARIFF_TYPE


async def process_tariff_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    query = update.callback_query
    await query.answer()

    tariff_map = {
        "tariff_1": "1 АКБ",
        "tariff_2": "2 АКБ",
        "tariff_buyout": "Выкуп"
    }
    context.user_data["new_tariff_type"] = tariff_map[query.data]

    if context.user_data["new_tariff_type"] == "Выкуп":
        msg = await query.message.reply_text("Введите количество недель до выкупа:")
        context.user_data["edit_message_ids"].append(msg.message_id)
        return INPUT_BUYOUT_WEEKS
    else:
        msg = await query.message.reply_text("Введите стоимость аренды в рублях за неделю:")
        context.user_data["edit_message_ids"].append(msg.message_id)
        return INPUT_WEEKLY_PRICE


async def process_buyout_weeks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    value = update.message.text.strip()
    if not value.isdigit() or int(value) <= 0:
        msg = await update.message.reply_text("Введите корректное количество недель (целое положительное число):")
        context.user_data["edit_message_ids"].append(msg.message_id)
        return INPUT_BUYOUT_WEEKS

    context.user_data["buyout_weeks"] = int(value)
    msg = await update.message.reply_text("Введите стоимость аренды в рублях за неделю:")
    context.user_data["edit_message_ids"].append(msg.message_id)
    return INPUT_WEEKLY_PRICE

async def process_weekly_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  
    scooter_id = context.user_data["selected_scooter_id"]
    value = update.message.text.strip()

    if not value.isdigit() or int(value) <= 0:
        msg = await update.message.reply_text("Введите корректную стоимость в рублях (целое положительное число):")
        context.user_data["edit_message_ids"].append(msg.message_id)
        return INPUT_WEEKLY_PRICE

    price = int(value)
    update_scooter_field(scooter_id, "tariff_type", context.user_data["new_tariff_type"])
    update_scooter_field(scooter_id, "weekly_price", price)

    if context.user_data["new_tariff_type"] == "Выкуп":
        update_scooter_field(scooter_id, "buyout_weeks", context.user_data["buyout_weeks"])
    else:
        update_scooter_field(scooter_id, "buyout_weeks", None)

    msg = await update.message.reply_text(
        f"✅ Тариф обновлён: {context.user_data['new_tariff_type']} — {price}₽/нед"
    )
    context.user_data["edit_message_ids"].append(msg.message_id)

    return await back_to_scooter_field_menu(update, context)

# === Доп. комплектация ===

async def choose_flags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context) 
    query = update.callback_query
    await query.answer()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Договор", callback_data="flag_has_contract")],
        [InlineKeyboardButton("🔑 Вторые ключи", callback_data="flag_has_second_keys")],
        [InlineKeyboardButton("📡 Датчик", callback_data="flag_has_tracker")],
        [InlineKeyboardButton("🛑 Ограничитель", callback_data="flag_has_limiter")],
        [InlineKeyboardButton("🚴‍♂️ Педали", callback_data="flag_has_pedals")],
        [InlineKeyboardButton("📶 ПСИМ", callback_data="flag_has_sim")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_scooter_fields")]
    ])

    msg = await query.message.reply_text("Выберите флаг:", reply_markup=keyboard)
    context.user_data["edit_message_ids"].append(msg.message_id)

    return CHOOSE_FLAGS


async def choose_flag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context) 
    query = update.callback_query
    await query.answer()

    field = query.data.replace("flag_", "")
    context.user_data["edit_flag_field"] = field

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да", callback_data="flag_value_true")],
        [InlineKeyboardButton("❌ Нет", callback_data="flag_value_false")]
    ])

    msg = await query.message.reply_text("Установите значение:", reply_markup=keyboard)
    context.user_data["edit_message_ids"].append(msg.message_id)

    return EDIT_FLAG


async def process_flag_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_edit_messages(update, context)  

    query = update.callback_query
    await query.answer()

    scooter_id = context.user_data["selected_scooter_id"]
    field = context.user_data["edit_flag_field"]
    value = query.data.endswith("true")

    update_scooter_field(scooter_id, field, value)

    msg = await query.message.reply_text(
        f"✅ {field} обновлён: {'✅ Да' if value else '❌ Нет'}"
    )
    context.user_data["edit_message_ids"].append(msg.message_id)

    return await choose_flags(update, context)

async def debug_unexpected_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[FSM] ⚠️ Получено сообщение в CHOOSE_FIELD, но оно не обрабатывается:", update.message.text)
    await update.message.reply_text("⚠️ Это сообщение не обработано. Вероятно, проблема с переходом состояния.")

# === FSM регистрация ===

edit_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(choose_section, pattern="^(edit_profile|edit_scooters)$")
    ],
    states={
        CHOOSE_SECTION: [
            CallbackQueryHandler(choose_section, pattern="^(edit_profile|edit_scooters)$"),
            CallbackQueryHandler(back_to_client_menu, pattern="^back_to_client_menu$"),
        ],

        CHOOSE_FIELD: [
            CallbackQueryHandler(choose_field, pattern="^edit_.*"),
            CallbackQueryHandler(back_to_client_menu, pattern="^back_to_client_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, debug_unexpected_text)
        ],

        EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_name)],
        EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_age)],
        EDIT_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_city)],
        EDIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
        EDIT_WORKPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_workplace)],

        CHOOSE_SCOOTER: [
            CallbackQueryHandler(choose_scooter, pattern="^scooter_id:\d+$"),
            CallbackQueryHandler(back_to_client_menu, pattern="^back_to_client_menu$")
        ],

        CHOOSE_SCOOTER_FIELD: [
            CallbackQueryHandler(choose_scooter_field, pattern="^field_.*"),
            CallbackQueryHandler(back_to_scooters_list, pattern="^back_to_scooters_list$")
        ],

        EDIT_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_model)],
        EDIT_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_vin)],
        EDIT_MOTOR_VIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_motor_vin)],
        EDIT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_issue_date)],

        SELECT_TARIFF_TYPE: [CallbackQueryHandler(process_tariff_type, pattern="^tariff_.*")],
        INPUT_BUYOUT_WEEKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_buyout_weeks)],
        INPUT_WEEKLY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_weekly_price)],

        CHOOSE_FLAGS: [
            CallbackQueryHandler(choose_flag, pattern="^flag_.*"),
            CallbackQueryHandler(back_to_scooter_field_menu, pattern="^back_to_scooter_fields$")
        ],
        EDIT_FLAG: [CallbackQueryHandler(process_flag_value, pattern="^flag_value_.*")],
    },
    fallbacks=[cancel_fallback],
    per_message=False
)
