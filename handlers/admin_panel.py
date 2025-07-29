import os

from telegram.error import BadRequest

from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto
from telegram.ext import (ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler,
                          filters, ConversationHandler)

from database.db import get_connection
from database.admins import is_admin, add_admin
from database.pending import get_all_pending_users
from database.clients import get_all_clients, get_client_by_tg_id, search_clients, get_custom_photos_by_client, delete_client_full
from database.repairs import get_all_pending_repairs, get_all_done_repairs, get_all_done_repairs_admin
from database.scooters import get_scooters_by_client, get_scooter_by_id
from database.payments import get_payments_by_scooter, save_payment_schedule_by_scooter, refresh_payment_schedule_by_scooter, get_last_and_next_friday, get_all_unpaid_clients_by_dates
from database.notes import get_notes, add_note
from database.postpone import get_all_postpones, get_active_postpones


from collections import defaultdict


from utils.payments_utils import format_payment_schedule
from utils.schedule_utils import get_next_fridays
from utils.cleanup import cleanup_admin_messages
from utils.time_utils import get_today

from handlers.cancel_handler import universal_cancel_handler, admin_back_handler
from handlers.admin_register import fill_callback
from handlers.admin_auth import admin_entry, check_admin_pin
from handlers.keyboard_utils import get_keyboard
from handlers.admin_register import admin_register_conv_handler
from handlers.register_client import cleanup_previous_messages


from datetime import datetime, timedelta, date




load_dotenv()

CLIENTS_PER_PAGE = 5
REPAIRS_PER_PAGE = 5
PAYMENTS_PER_PAGE = 5
EXTEND_ASK_WEEKS = 1001
SEARCH_CLIENT_QUERY, SELECT_SEARCH_RESULT = range(2)
NOTES_STATE = 2001  
PHOTO_COUNT, PHOTO_COLLECT = range(3101, 3103)


#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!#
#add_admin(tg_id=856550800, username="@xxxxxxxxxnxxxw", full_name="Толстов Андрей Русланович")


cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|/cancel|/start|/menu|/admin)$"),
    universal_cancel_handler
)


admin_back_fallback = MessageHandler(
    filters.Regex("^/back$"),
    admin_back_handler
)

async def admin_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.delete()
    return await start_search_client(update, context)


async def start_admin_fsm_from_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_admin_messages(update, context)

    tg_id = int(query.data.split(":")[1])
    context.user_data["tg_id_to_register"] = tg_id

    return await fill_callback(update, context)
   
async def pending_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_admin_messages(update, context)

    pending_users = get_all_pending_users()
    context.user_data.setdefault("admin_message_ids", [])

    if not pending_users:
        msg1 = await query.message.reply_text("📭 Пока нет необработанных заявок.")
        context.user_data["admin_message_ids"].append(msg1.message_id)

        back_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
        ])
        msg2 = await query.message.reply_text("⬅️ Вернуться в админ-панель:", reply_markup=back_keyboard)
        context.user_data["admin_message_ids"].append(msg2.message_id)
        return

    for user in pending_users:
        tg_id, username, name, age, city, phone, preferred_tariff, submitted_at = user

        text = (
            f"<b>{name}</b>, {age} лет\n"
            f"{city}\n"
            f"{phone}, {username or '--'}\n"
            f"Тариф: {preferred_tariff or 'не указан'}\n"
            f"📅 {submitted_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"<code>Telegram ID: {tg_id}</code>"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Приступить к заполнению", callback_data=f"fill:{tg_id}")]
        ])

        msg = await query.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
        context.user_data["admin_message_ids"].append(msg.message_id)

    
    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
    ])
    msg = await query.message.reply_text("⬅️ Вернуться в админ-панель:", reply_markup=back_keyboard)
    context.user_data["admin_message_ids"].append(msg.message_id)

async def handle_back_to_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cleanup_admin_messages(update, context)
    await show_clients_page(update, context, page=0)


async def show_clients_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    clients = get_all_clients()
    total = len(clients)
    pages = max(1, (total - 1) // CLIENTS_PER_PAGE + 1)

    if page < 0 or page >= pages:
        await update.callback_query.answer("Нет такой страницы.")
        return

    await cleanup_admin_messages(update, context)

    
    for msg_id in context.user_data.get("client_message_ids", []):
        try:
            await update.effective_chat.delete_message(msg_id)
        except:
            pass
    context.user_data["client_message_ids"] = []

    start = page * CLIENTS_PER_PAGE
    end = start + CLIENTS_PER_PAGE
    clients_slice = clients[start:end]

    for client in clients_slice:
        client_id = client["id"]
        photos = []
        custom_photos = get_custom_photos_by_client(client_id)

        if client.get("client_photo_id"):
            photos.append(InputMediaPhoto(client["client_photo_id"], caption="👤 Клиент"))

        if client.get("passport_main_id"):
            photos.append(InputMediaPhoto(client["passport_main_id"], caption="📄 Паспорт: главная"))

        if client.get("passport_address_id"):
            photos.append(InputMediaPhoto(client["passport_address_id"], caption="🏠 Паспорт: прописка"))

        for i, file_id in enumerate(custom_photos, start=1):
            photos.append(InputMediaPhoto(file_id, caption=f"📷 Доп. фото {i}"))

        if photos:
            if len(photos) == 1:
                msg_photo = await update.effective_chat.send_photo(
                photo=photos[0].media, caption=photos[0].caption
            )
           
            elif len(photos) > 1:
                media_msgs = await update.effective_chat.send_media_group(media=photos)
                for msg in media_msgs:
                    context.user_data.setdefault("client_message_ids", []).append(msg.message_id)

        text = (
            f"👤 <b>{client['full_name']}</b>, {client['age']} лет\n"
            f"📍 Город: {client['city']}\n"
            f"📞 Телефон: {client['phone']}\n"
            f"🏢 Работа: {client['workplace'] or '—'}\n"
            f"🆔 Telegram ID: <code>{client['telegram_id']}</code>\n"
            f"🧑‍💻 Username: {client['username'] or '—'}\n"
            f"\n<b>🛵 Скутеры клиента:</b>\n\n"
        )

        scooters = get_scooters_by_client(client_id)

        for idx, scooter in enumerate(scooters, start=1):
            if len(scooters) > 1 and idx > 1:
                text += "\n🔻🔻🔻🔻🔻🔻🔻🔻🔻\n\n"

            text += (
                f"<b>Скутер №{idx}:</b>\n"
                f"• Модель: {scooter['model']}\n"
                f"• VIN: {scooter['vin']}\n"
                f"• VIN мотора: {scooter['motor_vin']}\n"
                f"• Выдан: {scooter['issue_date'].strftime('%d.%m.%Y') if scooter['issue_date'] else '—'}\n"
                f"• Тариф: {scooter['tariff_type']}"
            )
            if scooter['tariff_type'] == "Выкуп" and scooter['buyout_weeks']:
                text += f" ({scooter['buyout_weeks']} нед.)"
            text += f" — {scooter['weekly_price']}₽/нед\n"

            text += "\n<b>🔧 Дополнительная комплектация:</b>\n"

            options = [
                f"📄 Договор: {'✅' if scooter['has_contract'] else '—'}",
                f"🔑 Вторые ключи: {'✅' if scooter['has_second_keys'] else '—'}",
                f"📡 Датчик: {'✅' if scooter['has_tracker'] else '—'}",
                f"🛑 Ограничитель: {'✅' if scooter['has_limiter'] else '—'}",
                f"🚲 Педали: {'✅' if scooter['has_pedals'] else '—'}",
                f"📶 ПЭСИМ: {'✅' if scooter['has_sim'] else '—'}"
            ]
            text += "\n" + "\n".join(options) + "\n"

            payments = get_payments_by_scooter(scooter['id'])
            postpones = get_active_postpones(scooter['id'])


            postpones_dicts = [
            {
            "original_date": row[0],
            "scheduled_date": row[1],
            "with_fine": row[2],
            "fine_amount": row[3],
            "requested_at": row[4]
            }
            for row in postpones
            ]

            text += format_payment_schedule(client['telegram_id'], payments, postpones_dicts)

        notes = get_notes(client_id)

        if notes:
            text += "\n\n📝 <b>Последние заметки:</b>\n\n"
            for note, created_at in notes:
                text += f"• {created_at.strftime('%d.%m.%Y')} — {note}\n"
        else:
            text += "\n\n📝 Заметок пока нет.\n\n"                

       
        keyboard = InlineKeyboardMarkup([
            [
            InlineKeyboardButton("⚙️ Редактировать", callback_data=f"edit_client:{client_id}"),
            InlineKeyboardButton("🔄 Продлить аренду", callback_data=f"extend_start:{client_id}")
            ],
            [InlineKeyboardButton("📷 Загрузить фото", callback_data=f"add_photos:{client_id}")
            ],
            [
            InlineKeyboardButton("🔧 Обновить график", callback_data=f"refresh_menu:{client_id}")
            ],
            [
            InlineKeyboardButton("📝 Добавить заметку", callback_data=f"notes:{client_id}"),
            InlineKeyboardButton("📄 Все заметки", callback_data=f"all_notes:{client_id}")
            ],
            [InlineKeyboardButton("❌ Удалить клиента", callback_data=f"delete_client:{client_id}")]
        ])
        msg = await update.effective_chat.send_message(text, parse_mode="HTML", reply_markup=keyboard)
        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)

# Навигация + кнопка назад
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"clients_page:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 Стр. {page + 1}/{pages}", callback_data="noop"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton("▶️ Вперёд", callback_data=f"clients_page:{page + 1}"))

# Кнопка назад в админку
    nav_buttons.append(InlineKeyboardButton("↩️ Назад", callback_data="admin_back"))

    nav_markup = InlineKeyboardMarkup([nav_buttons])
    nav_msg = await update.effective_chat.send_message("Навигация по клиентам:", reply_markup=nav_markup)
    context.user_data.setdefault("client_message_ids", []).append(nav_msg.message_id)



async def handle_clients_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cleanup_admin_messages(update, context)

    page = int(update.callback_query.data.split(":")[1])
    await show_clients_page(update, context, page=page)


async def repair_pending_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_admin_messages(update, context)

    requests = get_all_pending_repairs()
    context.user_data["admin_message_ids"] = []

    if not requests:
        msg1 = await update.effective_chat.send_message("📝 Нет необработанных ремонтных заявок.")
        context.user_data["admin_message_ids"].append(msg1.message_id)

        back_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
        ])
        msg2 = await update.effective_chat.send_message("⬅️ Вернуться в админ-панель:", reply_markup=back_keyboard)
        context.user_data["admin_message_ids"].append(msg2.message_id)
        return

    for req in requests:
        id, tg_id, username, name, city, phone, vin, problem, photo_file_id, submitted_at = req
        text = (
            f"<b>{name}</b> из {city}\n"
            f"{phone}, @{username}\n"
            f"🆔 VIN: {vin}\n"
            f"⚠️ Проблема: {problem}\n"
            f"📅 {submitted_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"<code>{tg_id}</code>"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛠 Назначить мастера", callback_data=f"assign_repair:{id}")]
        ])

        if photo_file_id:
            msg = await update.effective_chat.send_photo(
                photo=photo_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            msg = await update.effective_chat.send_message(
                text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

        context.user_data["admin_message_ids"].append(msg.message_id)

    # Добавляем кнопку "Назад" внизу
    back_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
    ])
    msg = await update.effective_chat.send_message("⬅️ Вернуться в админ-панель:", reply_markup=back_keyboard)
    context.user_data["admin_message_ids"].append(msg.message_id)

#Фото

async def start_photo_upload_flexible(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    client_id = int(query.data.split(":")[1])
    context.user_data["upload_photo_client_id"] = client_id

    await cleanup_admin_messages(update, context)

    msg = await query.message.reply_text("📷 Сколько фото вы хотите загрузить? Введите число:")
    context.user_data.setdefault("admin_messages", []).append(msg.message_id)

    return PHOTO_COUNT


async def ask_photo_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❗ Введите положительное число (например: 3)")
        return PHOTO_COUNT

    count = int(text)
    context.user_data["photo_total"] = count
    context.user_data["photo_step"] = 0
    context.user_data["photo_ids"] = []

    msg = await update.message.reply_text("📤 Отправьте фото 1 из " + str(count))
    context.user_data["admin_messages"].append(msg.message_id)

    return PHOTO_COLLECT


async def handle_flexible_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ Пожалуйста, отправьте именно фото.")
        return PHOTO_COLLECT

    file_id = update.message.photo[-1].file_id
    context.user_data["photo_ids"].append(file_id)
    context.user_data["photo_step"] += 1

    current = context.user_data["photo_step"]
    total = context.user_data["photo_total"]

    if current < total:
        msg = await update.message.reply_text(f"📤 Отправьте фото {current + 1} из {total}")
        context.user_data["admin_messages"].append(msg.message_id)
        return PHOTO_COLLECT

    # Сохраняем в отдельную таблицу

    client_id = context.user_data["upload_photo_client_id"]
    photos = context.user_data["photo_ids"]

    with get_connection() as conn:
        with conn.cursor() as cur:
            for file_id in photos:
                cur.execute("""
                    INSERT INTO client_photos (client_id, file_id, uploaded_at)
                    VALUES (%s, %s, NOW())
                """, (client_id, file_id))
        conn.commit()

    await cleanup_admin_messages(update, context)
    await update.message.reply_text("✅ Фото успешно добавлены!")

    return await back_to_selected_client(update, context)


async def show_done_repairs_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    repairs = get_all_done_repairs_admin()
    total = len(repairs)
    pages = (total - 1) // REPAIRS_PER_PAGE + 1

    if page < 0 or page >= pages:
        if update.callback_query:
            await update.callback_query.answer("Нет такой страницы.")
        return

    await cleanup_admin_messages(update, context)

    start = page * REPAIRS_PER_PAGE
    end = start + REPAIRS_PER_PAGE
    repairs_slice = repairs[start:end]

    for r in repairs_slice:
        id, tg_id, username, name, city, phone, vin, problem, photo_file_id, completed_at = r

        text = (
            f"✅ <b>Завершённая заявка</b>\n"
            f"👤 <b>{name}</b> из {city}\n"
            f"📞 {phone}, @{username or '—'}\n"
            f"🪪 VIN: {vin}\n"
            f"⚠️ Проблема: {problem}\n"
            f"📆 Завершено: {completed_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"<code>{tg_id}</code>"
        )

        if photo_file_id:
            msg = await update.effective_chat.send_photo(
                photo=photo_file_id,
                caption=text,
                parse_mode="HTML"
            )
        else:
            msg = await update.effective_chat.send_message(
                text,
                parse_mode="HTML"
            )

        context.user_data.setdefault("admin_message_ids", []).append(msg.message_id)

    # Пагинация + кнопка назад
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"repairs_page:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 Стр. {page + 1}/{pages}", callback_data="noop"))
    if end < total:
        nav_buttons.append(InlineKeyboardButton("▶️ Вперёд", callback_data=f"repairs_page:{page + 1}"))

    # Кнопка назад в админку
    nav_buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))

    nav_markup = InlineKeyboardMarkup([nav_buttons])
    nav_msg = await update.effective_chat.send_message("Навигация по ремонтам:", reply_markup=nav_markup)
    context.user_data["admin_message_ids"].append(nav_msg.message_id)

    

async def done_repairs_list_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_done_repairs_page(update, context, page=0)


async def handle_repairs_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = int(update.callback_query.data.split(":")[1])
    await show_done_repairs_page(update, context, page=page)


#Продление аренды
async def extend_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    client_id = int(query.data.split(":")[1])
    context.user_data["extend_client_id"] = client_id

    scooters = get_scooters_by_client(client_id)
    if not scooters:
        await cleanup_admin_messages(update, context)
        msg = await query.message.reply_text("❗ У этого клиента нет зарегистрированных скутеров.")
        context.user_data.setdefault("admin_messages", []).append(msg.message_id)
        return ConversationHandler.END

    if len(scooters) == 1:
        
        scooter_id = scooters[0]['id']
        context.user_data["extend_scooter_id"] = scooter_id
        await cleanup_admin_messages(update, context)

        msg = await query.message.reply_text(
        "🔁 На сколько недель вперёд продлить аренду? Введите число:")
   
        context.user_data.setdefault("admin_messages", []).append(msg.message_id)
        return EXTEND_ASK_WEEKS

    
    keyboard = [
        [InlineKeyboardButton(f"Скутер {idx+1}: VIN {s['vin']}", callback_data=f"select_scooter:{s['id']}")]
        for idx, s in enumerate(scooters)
    ]
    await cleanup_admin_messages(update, context)
    msg = await query.message.reply_text(
        "У клиента несколько скутеров. Выберите, для какого продлить аренду:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.setdefault("admin_messages", []).append(msg.message_id)

    return ConversationHandler.END

async def select_scooter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_admin_messages(update, context)
    query = update.callback_query
    await query.answer()

    scooter_id = int(query.data.split(":")[1])
    context.user_data["extend_scooter_id"] = scooter_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_back_client")]
    ])

    msg = await query.message.reply_text(
        "🔁 На сколько недель вперёд продлить аренду? Введите число:\n\n"
        "Если вы ошиблись, нажмите «Назад», чтобы вернуться к карточке клиента.",
        reply_markup=keyboard
    )

    context.user_data.setdefault("admin_messages", []).append(msg.message_id)
    return EXTEND_ASK_WEEKS

async def extend_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❗ Введите положительное число (например: 5)")
        return EXTEND_ASK_WEEKS

    weeks = int(text)
    scooter_id = context.user_data.get("extend_scooter_id")

    if not scooter_id:
        await update.message.reply_text("⚠️ Не выбран самокат для продления.")
        return ConversationHandler.END

    payments = get_payments_by_scooter(scooter_id)
    if not payments:
        await update.message.reply_text("❗ Нет графика платежей для этого скутера.")
        return ConversationHandler.END

    last_date = max(p[1] for p in payments)
    start_date = last_date + timedelta(days=1)
    new_dates = get_next_fridays(start_date, weeks)

    scooters = get_scooters_by_client(context.user_data["extend_client_id"])
    scooter = next((s for s in scooters if s['id'] == scooter_id), None)

    if not scooter:
        await update.message.reply_text("⚠️ Не удалось найти данные по скутеру.")
        return ConversationHandler.END

    weekly_price = scooter['weekly_price']

    # Запись новых платежей
    save_payment_schedule_by_scooter(scooter_id, new_dates, weekly_price)

    await cleanup_admin_messages(update, context)

    await update.message.reply_text(
    f"✅ Аренда продлена ещё на {weeks} недель (до {new_dates[-1].strftime('%d.%m.%Y')})"
)

    await back_to_selected_client(update, context)
    return ConversationHandler.END

#Обновление графика аренды
async def refresh_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    client_id = int(query.data.split(":")[1])
    scooters = get_scooters_by_client(client_id)

    if not scooters:
        await cleanup_admin_messages(update, context)
        msg = await query.message.reply_text("❗🛴 У клиента нет скутеров.")
        context.user_data.setdefault("admin_messages", []).append(msg.message_id)
        return

    keyboard = []
    for idx, scooter in enumerate(scooters, start=1):
        button_text = f"↳ Скутер {idx}: VIN {scooter['vin']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"refresh_scooter:{scooter['id']}")])

    # Добавляем кнопку "Назад" в конец
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="admin_back_client")])

    await cleanup_admin_messages(update, context)

    msg = await query.message.reply_text(
        "Выберите для какого скутера обновить график:\n\n"
        "Если хотите вернуться на страницу клиента — нажмите «Назад».",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data.setdefault("admin_messages", []).append(msg.message_id)


async def refresh_scooter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    scooter_id = int(query.data.split(":")[1])
    scooter = get_scooter_by_id(scooter_id)

    if not scooter:
        await query.message.reply_text("❗ Скутер не найден.")
        return

    weekly_price = scooter['weekly_price']
    if scooter['tariff_type'] == "Выкуп" and scooter['buyout_weeks']:
        full_weeks_count = scooter['buyout_weeks']
    else:
        full_weeks_count = 10

    payments = get_payments_by_scooter(scooter_id)
    paid_payments = [p for p in payments if p[2] is True]

    if paid_payments:
        # ✅ если есть оплаченные платежи — график продолжаем от последней оплаты
        last_paid_date = max(p[0] for p in paid_payments)
        start_date = last_paid_date + timedelta(days=7)

    else:
        # ✅ если оплат ещё не было — строим график от ДАТЫ ВЫДАЧИ
        issue_date = scooter.get("issue_date")
        if not issue_date:
            await query.message.reply_text("❗ У скутера не указана дата выдачи.")
            return

        weekday_issue = issue_date.weekday()  # 0-пн ... 6-вс

        # 1️⃣ ближайшая пятница после даты выдачи
        days_to_friday = (4 - weekday_issue) % 7
        first_friday = issue_date + timedelta(days=days_to_friday)

        # 2️⃣ если выдача была ПН–ПТ → первая оплата только на следующей неделе
        if weekday_issue <= 4:
            first_friday += timedelta(weeks=1)

        start_date = first_friday

    # ✅ Вычисляем сколько недель надо вставить
    if scooter['tariff_type'] == "Выкуп":
        paid_weeks = len(paid_payments)
        remaining_weeks = full_weeks_count - paid_weeks
    else:
        remaining_weeks = full_weeks_count

    # 🔥 Теперь перед обновлением удаляем только неоплаченные платежи, но не «сдвигаем» первую пятницу дальше!
    refresh_payment_schedule_by_scooter(scooter_id, start_date, remaining_weeks, weekly_price)

    await cleanup_admin_messages(update, context)
    msg = await query.message.reply_text("✅ График платежей обновлён!")
    context.user_data.setdefault("admin_messages", []).append(msg.message_id)

    return await back_to_selected_client(update, context)

    
#Неоплаченные платежи

async def show_unpaid_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today()
    last_friday, next_friday = get_last_and_next_friday(today)

    unpaid = get_all_unpaid_clients_by_dates([last_friday, next_friday])
    if not unpaid:
        await update.callback_query.message.edit_text(
            "✅ Все платежи оплачены.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
            ])
        )
        return

    # Получаем все активные переносы
    active_postpones = get_all_postpones()
    postpones_dict = {}
    for tg_id, scooter_id, original_date, scheduled_date, with_fine, fine_amount, is_closed, requested_at in active_postpones:
        postpones_dict[original_date] = (scheduled_date, with_fine, fine_amount)

    overdue, today_unpaid, upcoming = [], [], []

    for full_name, phone, username, payment_date, amount in unpaid:
        uname = f"{username}" if username else phone
        base_line = f"• *{full_name}* [{uname}] — `{payment_date.strftime('%d.%m.%Y')}` — *{amount}₽*"

        # Проверка: есть ли перенос
        if payment_date in postpones_dict:
            scheduled_date, with_fine, fine_amount = postpones_dict[payment_date]
            fine_text = f" (штраф: {fine_amount}₽)" if with_fine else ""
            base_line += f"\n🔁 Перенесён на `{scheduled_date.strftime('%d.%m.%Y')}`{fine_text}"

        if payment_date == today and today.weekday() == 4:  # сегодня пятница
            today_unpaid.append(base_line)
        elif payment_date < today:
            overdue.append(base_line)
        else:
            upcoming.append(base_line)

    parts = ["📋 *Неоплаченные платежи:*\n"]
    if today_unpaid:
            parts.append("🟠 *Ещё не оплачены (сегодня):*\n" + "\n".join(today_unpaid))
    if overdue:
        parts.append("🔴 *Просрочено:*\n" + "\n".join(overdue))
    if upcoming:
        parts.append("🟡 *К следующей пятнице:*\n" + "\n".join(upcoming))

    text = "\n\n".join(parts)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="unpaid_payments")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
    ])

    try:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            await update.callback_query.answer("Нет новых изменений.", show_alert=True)
        else:
            raise
#Заметки
async def open_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_admin_messages(update, context)

    client_id = int(query.data.split(":")[1])
    context.user_data["notes_client_id"] = client_id

   
    msg = await query.message.reply_text("📝 Введите текст новой заметки:")

    context.user_data.setdefault("admin_messages", []).append(msg.message_id)

    return NOTES_STATE

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    client_id = context.user_data["notes_client_id"]

    add_note(client_id, text)

    await cleanup_admin_messages(update, context)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")]
    ])

    msg = await update.effective_chat.send_message(
        "✅ Заметка добавлена!",
        reply_markup=keyboard
    )
    context.user_data.setdefault("admin_messages", []).append(msg.message_id)

    return ConversationHandler.END


async def show_all_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_admin_messages(update, context) 

    client_id = int(query.data.split(":")[1])
   
    notes = get_notes(client_id, limit=50)

    if not notes:
        msg = await query.message.reply_text("⚠️ У клиента пока нет заметок.")
        context.user_data.setdefault("admin_messages", []).append(msg.message_id)
        return

    text = "<b>📒 Полная история заметок:</b>\n\n"
    for note, created_at in notes:
        text += f"{created_at.strftime('%d.%m.%Y %H:%M')} – {note}\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_back_client")]
    ])

    msg = await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    context.user_data.setdefault("admin_messages", []).append(msg.message_id)



#Поиск клиента

async def start_search_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_admin_messages(update, context)

    if update.message:
        msg = await update.message.reply_text("Введите имя, телефон, город, Telegram ID или username для поиска:")
    elif update.callback_query:
        await update.callback_query.answer()
        msg = await update.callback_query.message.reply_text("Введите имя, телефон, город, Telegram ID или username для поиска:\n\n" \
        "Если хотите вернуться в админ панель - пропишите команду /back")

    context.user_data.setdefault("admin_message_ids", []).append(msg.message_id)
    return SEARCH_CLIENT_QUERY


async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("FSM: Вошли в process_search_query")
    print("FSM (DEBUG): получен текст:", update.message.text)
    print("context:", context.user_data)
    query = update.message.text.strip()
    results = search_clients(query)

    await cleanup_admin_messages(update, context)

    if not results:
        msg1 = await update.effective_chat.send_message("❌ Клиенты не найдены.")
        msg2 = await update.effective_chat.send_message("🔁 Попробуйте еще раз:")
        context.user_data.setdefault("admin_message_ids", []).extend([msg1.message_id, msg2.message_id])
        return SEARCH_CLIENT_QUERY  

    
    context.user_data["search_results"] = results

    text = "Найдено клиентов:\n\n"
    for idx, client in enumerate(results, start=1):
        text += f"{idx}. {client['full_name']} ({client['city']}), {client['phone']}\n"

    msg1 = await update.effective_chat.send_message(text)
    msg2 = await update.effective_chat.send_message("📄 Введите номер клиента для просмотра:")

    context.user_data.setdefault("admin_message_ids", []).extend([msg1.message_id, msg2.message_id])
    


    return SELECT_SEARCH_RESULT



async def show_single_client(update: Update, context: ContextTypes.DEFAULT_TYPE, client_id: int):
    await cleanup_admin_messages(update, context)

    clients = get_all_clients()
    client = next((c for c in clients if c["id"] == client_id), None)

    if not client:
        await update.effective_chat.send_message("❌ Клиент не найден.")
        return

    
    text = (
        f"👤 <b>{client['full_name']}</b>, {client['age']} лет\n"
        f"📍 Город: {client['city']}\n"
        f"📞 Телефон: {client['phone']}\n"
        f"🏢 Работа: {client['workplace'] or '—'}\n"
        f"🆔 Telegram ID: <code>{client['telegram_id']}</code>\n"
        f"🧑‍💻 Username: {client['username'] if client['username'].startswith('@') else '@' + client['username'] if client['username'] else '—'}\n"
        f"\n<b>🛵 Скутеры клиента:</b>\n\n"
    )

    scooters = get_scooters_by_client(client_id)

    for idx, scooter in enumerate(scooters, start=1):
        if len(scooters) > 1 and idx > 1:
            text += "\n🔻🔻🔻🔻🔻🔻🔻🔻🔻\n\n"

        text += (
            f"<b>Скутер №{idx}:</b>\n"
            f"• Модель: {scooter['model']}\n"
            f"• VIN: {scooter['vin']}\n"
            f"• VIN мотора: {scooter['motor_vin']}\n"
            f"• Выдан: {scooter['issue_date'].strftime('%d.%m.%Y') if scooter['issue_date'] else '—'}\n"
            f"• Тариф: {scooter['tariff_type']}"
        )
        if scooter['tariff_type'] == "Выкуп" and scooter['buyout_weeks']:
            text += f" ({scooter['buyout_weeks']} нед.)"
        text += f" — {scooter['weekly_price']}₽/нед\n"

        text += "\n<b>🔧 Дополнительная комплектация:</b>\n"
        options = [
            f"📄 Договор: {'✅' if scooter['has_contract'] else '—'}",
            f"🔑 Вторые ключи: {'✅' if scooter['has_second_keys'] else '—'}",
            f"📡 Датчик: {'✅' if scooter['has_tracker'] else '—'}",
            f"🛑 Ограничитель: {'✅' if scooter['has_limiter'] else '—'}",
            f"🚲 Педали: {'✅' if scooter['has_pedals'] else '—'}",
            f"📶 ПЭСИМ: {'✅' if scooter['has_sim'] else '—'}"
        ]
        text += "\n" + "\n".join(options) + "\n"

        payments = get_payments_by_scooter(scooter['id'])
        postpones = get_active_postpones(scooter['id'])


        postpones_dicts = [
        {   
        "original_date": row[0],
        "scheduled_date": row[1],
        "with_fine": row[2],
        "fine_amount": row[3],
        "requested_at": row[4]
        }
        for row in postpones
        ]

        text += format_payment_schedule(client['telegram_id'], payments, postpones_dicts)
    notes = get_notes(client_id)

    if notes:
        text += "\n\n📝 <b>Последние заметки:</b>\n\n"
        for note, created_at in notes:
            text += f"• {created_at.strftime('%d.%m.%Y')} — {note}\n"
    else:
        text += "\n\n📝 Заметок пока нет.\n\n"

    keyboard = InlineKeyboardMarkup([
            [
            InlineKeyboardButton("⚙️ Редактировать", callback_data=f"edit_client:{client_id}"),
            InlineKeyboardButton("🔄 Продлить аренду", callback_data=f"extend_start:{client_id}")
            ],
            [InlineKeyboardButton("📷 Загрузить фото", callback_data=f"add_photos:{client_id}")
            ],
            [
            InlineKeyboardButton("🔧 Обновить график", callback_data=f"refresh_menu:{client_id}")
            ],
            [
            InlineKeyboardButton("📝 Добавить заметку", callback_data=f"notes:{client_id}"),
            InlineKeyboardButton("📄 Все заметки", callback_data=f"all_notes:{client_id}")
            ],
            [InlineKeyboardButton("❌ Удалить клиента", callback_data=f"delete_client:{client_id}")],
            [   
            InlineKeyboardButton("🔙 Назад", callback_data="admin_back")
            ]  
        ])
        
    
    custom_photos = get_custom_photos_by_client(client_id)
    standard_photos = []

    if client.get("client_photo_id"):
            standard_photos.append(InputMediaPhoto(client["client_photo_id"], caption="👤 Клиент"))
    if client.get("passport_main_id"):
            standard_photos.append(InputMediaPhoto(client["passport_main_id"], caption="📄 Паспорт: главная"))
    if client.get("passport_address_id"):
            standard_photos.append(InputMediaPhoto(client["passport_address_id"], caption="🏠 Паспорт: прописка"))


    for i, file_id in enumerate(custom_photos, start=1):
            standard_photos.append(InputMediaPhoto(file_id, caption=f"📷 Доп. фото {i}"))

            if standard_photos:
                if len(standard_photos) == 1:
                    msg = await update.effective_chat.send_photo(
                    photo=standard_photos[0].media, caption=standard_photos[0].caption
        )
                    context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
    else:
                    msgs = await update.effective_chat.send_media_group(media=standard_photos)
                    for msg in msgs:
                        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)  


    msg = await update.effective_chat.send_message(text, parse_mode="HTML", reply_markup=keyboard)
    #context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
    context.user_data["came_from_search"] = True
    context.user_data["client_id"] = client_id  



async def process_search_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("FSM (DEBUG): вошли в process_search_selection")
    print("FSM (DEBUG): получен выбор:", update.message.text)
    choice = update.message.text.strip()

    if not choice.isdigit():
        await cleanup_admin_messages(update, context)
        msg = await update.effective_chat.send_message("Введите номер клиента из списка.")
        context.user_data.setdefault("admin_message_ids", []).append(msg.message_id)
        return SELECT_SEARCH_RESULT

    idx = int(choice) - 1
    results = context.user_data.get("search_results", [])

    if idx < 0 or idx >= len(results):
        await cleanup_admin_messages(update, context)
        msg = await update.effective_chat.send_message("Некорректный номер.")
        context.user_data.setdefault("admin_message_ids", []).append(msg.message_id)
        return SELECT_SEARCH_RESULT

    client_id = results[idx]["id"]
    context.user_data["client_id"] = client_id
    context.user_data["came_from_search"] = True

    await show_single_client(update, context, client_id)
    context.user_data.pop("search_results", None)
    return ConversationHandler.END

async def back_to_selected_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    for key in ["notes_client_id", "extend_client_id", "extend_scooter_id"]:
        context.user_data.pop(key, None)

    for msg_id in context.user_data.get("client_message_ids", []):
        try:
            await update.effective_chat.delete_message(msg_id)
        except:
            pass
    context.user_data["client_message_ids"] = []

    if context.user_data.get("came_from_search"):
        client_id = context.user_data.get("client_id")
        if client_id:
            await show_single_client(update, context, client_id)
            return ConversationHandler.END

    page = context.user_data.get("current_page", 0)
    await show_clients_page(update, context, page=page)
    return ConversationHandler.END

async def handle_admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    
    for key in ["admin_message_ids", "client_message_ids"]:
        for msg_id in context.user_data.get(key, []):
            try:
                await update.effective_chat.delete_message(msg_id)
            except:
                pass
        context.user_data[key] = []

    
    await admin_entry(update, context)

async def go_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.delete()
    await update.effective_chat.send_message(
        "⚡ Приветствую, дорогой друг! Это бот компании Ibilsh — твоего помощника в мире электровелосипедов!\n\n"
        "🔹 Хочешь к нам в команду? — Оформим заявку на твой новенький электровело в пару кликов!\n"
        "🔹 Что-то сломалось? — Мастер будет у тебя через несколько часов!\n"
        "🔹 Уже с нами? — Загляни в личный кабинет!\n"
        "🔹 Появились вопросы? — Мы собрали часто задаваемые вопросы и ответы на них!\n\n"
        "👇 Выбери, что тебе нужно:",
        reply_markup=get_keyboard()
    )


#Удаление клиента

async def handle_delete_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_id = int(update.callback_query.data.split(":")[1])
    delete_client_full(client_id)
    await update.callback_query.answer("Клиент удалён.")
    await update.callback_query.message.edit_text("✅ Клиент полностью удалён из базы.")

# --- Регистрация хендлеров ---

def register_admin_handlers(app):
    app.add_handler(CommandHandler("admin", admin_entry))
    app.add_handler(CallbackQueryHandler(pending_requests_list, pattern="^admin_pending$"))
    app.add_handler(CallbackQueryHandler(start_admin_fsm_from_pending, pattern=r"^fill:\d+$"))
    app.add_handler(CallbackQueryHandler(refresh_menu, pattern=r"^refresh_menu:\d+$"))
    app.add_handler(CallbackQueryHandler(refresh_scooter, pattern=r"^refresh_scooter:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_back_to_clients, pattern="^back_to_clients$"))
    app.add_handler(CallbackQueryHandler(back_to_selected_client, pattern="^admin_back_client$"))
    app.add_handler(CallbackQueryHandler(handle_admin_back, pattern="^admin_back$"))
    app.add_handler(CallbackQueryHandler(handle_delete_client, pattern=r"^delete_client:(\d+)$"))
    app.add_handler(CallbackQueryHandler(show_unpaid_payments, pattern="^unpaid_payments$"))
    app.add_handler(CallbackQueryHandler(go_to_main_menu, pattern="^admin_to_main$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: show_clients_page(u, c, page=0), pattern="^admin_all_clients$"))
    app.add_handler(CallbackQueryHandler(handle_clients_pagination, pattern=r"^clients_page:\d+$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer("Навигация"), pattern="^noop$"))
    app.add_handler(CallbackQueryHandler(repair_pending_requests_list, pattern="^admin_pending_repairs$"))
    app.add_handler(CallbackQueryHandler(done_repairs_list_entry, pattern="^admin_done_repairs$"))
    app.add_handler(CallbackQueryHandler(handle_repairs_pagination, pattern=r"^repairs_page:\d+$"))
    app.add_handler(CallbackQueryHandler(show_all_notes, pattern=r"^all_notes:\d+$"))
    
    

    extend_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(extend_start, pattern=r"^extend_start:\d+$"),
        CallbackQueryHandler(select_scooter_callback, pattern=r"^select_scooter:\d+$")
    ],
    states={
        EXTEND_ASK_WEEKS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, extend_save)
        ],
    },
    fallbacks=[
        cancel_fallback,
        CallbackQueryHandler(back_to_selected_client, pattern="^admin_back_client$")
    ],)

    app.add_handler(extend_conv_handler)
    
    

    search_conv = ConversationHandler(
    entry_points=[
        CommandHandler("search", start_search_client),
        CallbackQueryHandler(admin_search_callback, pattern="^admin_search$")  
    ],
    states={
        SEARCH_CLIENT_QUERY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_query)
        ],
        SELECT_SEARCH_RESULT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_search_selection)
        ],
    },
    fallbacks=[cancel_fallback, admin_back_fallback]

)
    app.add_handler(search_conv)


    photo_flexible_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_photo_upload_flexible, pattern=r"^add_photos:\d+$")],
    states={
        PHOTO_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_photo_count)],
        PHOTO_COLLECT: [MessageHandler(filters.PHOTO, handle_flexible_photo)]
    },
    fallbacks=[CallbackQueryHandler(back_to_selected_client, pattern="^admin_back_client$")]
)
    app.add_handler(photo_flexible_conv)        



    notes_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(open_notes, pattern="^notes:\d+$"),
    ],
    states={
        NOTES_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_note)]
    },
    fallbacks=[
        CallbackQueryHandler(back_to_selected_client, pattern="^admin_back_client$")
    ]
)
    app.add_handler(notes_conv_handler)
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_admin_pin))

