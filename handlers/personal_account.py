from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.error import BadRequest

from datetime import datetime

from collections import defaultdict

from services.notifier import notify_admin_about_postpone
from services.google_sheets import log_payment_postpone

import uuid

from dotenv import load_dotenv

from database.db import get_connection
from database.users import check_user, get_user_info
from database.clients import get_client_by_tg_id
from database.repairs import  get_all_done_repairs
from database.postpone import save_postpone_request, get_postpone_for_date, get_active_postpones, has_active_postpone, get_postpone_dates_by_tg_id, close_postpone
from database.scooters import get_scooters_by_client, get_scooter_by_id
from database.payments import get_unpaid_payments_by_scooter, get_payments_by_scooter, update_payment_amount,  save_payment_schedule_by_scooter, mark_payments_as_paid

from handlers.cancel_handler import universal_cancel_handler, exit_lk_handler
from handlers.register_client import cleanup_previous_messages
from handlers.keyboard_utils import get_keyboard
from handlers.admin_edit import cleanup_client_messages

from services.yookassa_service import create_payment

from utils.payments_utils import format_payment_schedule, get_payment_id_by_date
from utils.time_utils import get_today
from utils.cleanup import cleanup_lk_messages
from utils.schedule_utils import get_next_fridays
from utils.notify_utils import payment_confirm_registry


from datetime import date, timedelta



load_dotenv()

ASK_NAME, ASK_PHONE=range(2)

ASK_WEEKS = 101

ASK_WEEKS_NEW_ALL = 3001

CONFIRM_POSTPONE = 1

PERSONAL_MENU = 100

cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|выход|/start|/menu)$"),
    universal_cancel_handler
)


payment_back_fallback = MessageHandler(
    filters.Regex("^/exit$"),
    exit_lk_handler
)

async def handle_back_silent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_lk_messages(update, context)
    await update.callback_query.answer()


async def go_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    keyboard = get_keyboard()
    text = (
        "⚡ Приветствую, дорогой друг! Это бот компании Ibilsh — твоего помощника в мире электровелосипедов!\n\n"
        "🔹 Хочешь к нам в команду? — Оформим заявку на твой новенький электровело в пару кликов!\n"
        "🔹 Что-то сломалось? — Мастер будет у тебя через несколько часов!\n"
        "🔹 Уже с нами? — Загляни в личный кабинет!\n"
        "🔹 Появились вопросы? — Мы собрали часто задаваемые вопросы и ответы на них!\n\n"
        "👇 Выбери, что тебе нужно:"
    )

    try:
        await update.callback_query.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        # Если сообщение слишком старое или было удалено, fallback на send_message
        await update.effective_chat.send_message(text, reply_markup=keyboard)


async def back_to_personal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cleanup_lk_messages(update, context)
    await personal_account_entry(update, context)


async def exit_to_personal_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очистка личных сообщений (удаление или редактирование, если требуется)
    await cleanup_lk_messages(update, context)

    # Отображение главного меню ЛК
    await personal_account_entry(update, context)    



async def personal_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return PERSONAL_MENU

async def personal_account_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message
    context.user_data["start_message_id"] = message.message_id  # ✅ фиксируем ID

    #await cleanup_previous_messages(update, context)
    await cleanup_lk_messages(update, context)
    await cleanup_client_messages(update, context)

    user = update.effective_user
    tg_id = user.id

    if not check_user(tg_id):
        try:
            await message.edit_text(
                "🔒 Основной функционал личного кабинета пока недоступен.\n"
                "Вы пока не арендуете скутер через компанию Ibilsh.\n\n"
                "⚠️ Станьте частью нашей команды — и доступ к ЛК откроется!"
            )
        except:
            msg = await message.reply_text(
                "🔒 Основной функционал личного кабинета пока недоступен.\n"
                "Вы пока не арендуете скутер через компанию Ibilsh.\n\n"
                "⚠️ Станьте частью нашей команды — и доступ к ЛК откроется!"
            )
            context.user_data["lk_message_ids"].append(msg.message_id)
        return

    user_data = get_user_info(tg_id)

    text = (
        f"✅ Добро пожаловать, {user_data['full_name']}!\n"
        f"📦 Ваш статус: <b>аренда активна</b>\n\n"
        f"⚙️ Вы можете:\n"
        f"• Просмотреть основную информацию согласно вашему тарифу по аренде\n"
        f"• Просмотреть график и статус платежей\n"
        f"• Загрузить подтверждение оплаты\n"
        f"• Просмотреть историю ремонтов, обратиться к администратору при необходимости\n"
        f"• Перенести оплату на следующую неделю\n\n"
        f"<b>📌 Выберите интересующий раздел:</b>"
    )

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛵 Статус аренды", callback_data="status")],
        [InlineKeyboardButton("🛠 История ремонтов", callback_data="repairs")],
        [InlineKeyboardButton("📅 График платежей", callback_data="payments")],
        [InlineKeyboardButton("💸 Оплатить аренду", callback_data="pay_all")],
        [InlineKeyboardButton("📅 Перенести платёж", callback_data="postpone")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="client_to_main")]
    ])

    try:
        msg = await message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        context.user_data["main_message_id"] = msg.message_id
    except Exception as e:
        # fallback — если сообщение не редактируется (например, старое)
        msg = await message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        context.user_data["main_message_id"] = msg.message_id




async def personal_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await personal_account_entry(update, context)

async def handle_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_status(update, context)

async def handle_repairs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await handle_repair_history(update, context)


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    client = get_client_by_tg_id(tg_id)

    if not client:
        msg = await update.callback_query.message.reply_text("⚠️ Не удалось найти клиента.")
        context.user_data.setdefault("lk_message_ids", []).append(msg.message_id)
        return

    client_id = client["id"]
    scooters = get_scooters_by_client(client_id)
    username = client['username'] or "-"

    text = (
        f"👤 <b>{client['full_name']}</b>, {client['age']} лет\n"
        f"📞 Телефон: {client['phone']}\n"
        f"🏢 Работа: {client['workplace'] or '—'}\n"
        f"🆔 Telegram ID: <code>{tg_id}</code>\n"
        f"👤 Username: {username}\n"
        f"\n<b>🛵 Скутеры:</b>\n"
    )

    for idx, scooter in enumerate(scooters, 1):
        tariff_line = scooter['tariff_type']
        if scooter['tariff_type'] == "Выкуп" and scooter['buyout_weeks']:
            tariff_line += f" ({scooter['buyout_weeks']} нед.)"
        tariff_line += f" — {scooter['weekly_price']}₽/нед"

        options = [
            f"📄 Договор: {'✅' if scooter['has_contract'] else '❌'}",
            f"🔑 Вторые ключи: {'✅' if scooter['has_second_keys'] else '❌'}",
            f"📡 Датчик: {'✅' if scooter['has_tracker'] else '❌'}",
            f"🛑 Ограничитель: {'✅' if scooter['has_limiter'] else '❌'}",
            f"🚲 Педали: {'✅' if scooter['has_pedals'] else '❌'}",
            f"📶 ПЭСИМ: {'✅' if scooter['has_sim'] else '❌'}"
        ]

        text += (
            f"\n<b>Скутер №{idx}:</b>\n"
            f"• Модель: {scooter['model']}\n"
            f"• VIN: {scooter['vin']}\n"
            f"• VIN мотора: {scooter['motor_vin']}\n"
            f"• Выдан: {scooter['issue_date'].strftime('%d.%m.%Y')}\n"
            f"• Тариф: {tariff_line}\n"
            f"{chr(10).join(options)}\n"
        )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ])

    # 👉 если main_message_id уже есть — редактируем
    if "main_message_id" in context.user_data:
        await cleanup_lk_messages(update, context, new_text=text, reply_markup=keyboard)
    else:
        msg = await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        context.user_data["main_message_id"] = msg.message_id


async def handle_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    tg_id = update.effective_user.id

    client = get_client_by_tg_id(tg_id)
    if not client:
        msg = await update.callback_query.message.reply_text("❌ Не удалось найти клиента.")
        context.user_data.setdefault("lk_message_ids", []).append(msg.message_id)
        return

    client_id = client["id"]
    scooters = get_scooters_by_client(client_id)

    text = "<b>📅 Ваш график платежей:</b>\n"
    keyboard_buttons = []

    for idx, scooter in enumerate(scooters, 1):
        payments = get_payments_by_scooter(scooter["id"])
        postpones = get_active_postpones(scooter["id"])  # ✅ получаем переносы с нужными полями

        # Оборачиваем их в словари вручную, чтобы передать в format_payment_schedule
        postpones_dicts = [
            {
                "original_date": row[0],
                "scheduled_date": row[1],
                "with_fine": row[2],
                "fine_amount": row[3],
                "requested_at": row[4],
            }
            for row in postpones
        ]

        schedule = format_payment_schedule(tg_id, payments, postpones_dicts)
        text += f"\n📋<b>Скутер №{idx}:</b>\n{schedule}\n"

    keyboard_buttons = [
    [InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    if "main_message_id" in context.user_data:
        await cleanup_lk_messages(update, context, new_text=text, reply_markup=reply_markup)
    else:
        msg = await update.callback_query.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        context.user_data["main_message_id"] = msg.message_id
   

# Старт оплаты по нажатию на кнопку "Оплатить"

async def handle_pay_all_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_id = query.from_user.id
    client = get_client_by_tg_id(tg_id)
    if not client:
        await query.message.reply_text("❌ Не удалось найти клиента.")
        return ConversationHandler.END

    scooters = get_scooters_by_client(client["id"])
    all_unpaid = []
    today = get_today()
    active_postpones = []

    for scooter in scooters:
        unpaid = get_unpaid_payments_by_scooter(scooter["id"])
        for row in unpaid:
            all_unpaid.append((scooter, row))
            # ищем перенос именно по этой дате платежа
            postpone_row = get_postpone_for_date(scooter["id"], row[1])
            if postpone_row:
                active_postpones.append({
                    "scooter": scooter,
                    "payment": row,
                    "postpone": postpone_row,
                })

    if not all_unpaid:
        await query.message.reply_text("✅ У вас нет неоплаченных платежей.")
        return ConversationHandler.END

    # === 1. Просроченные платежи ===
    original_dates, scheduled_dates = get_postpone_dates_by_tg_id(tg_id)

    overdue_rows = []
    for scooter, row in all_unpaid:
        payment_date = row[1]

        # Если платёж перенесён, пропускаем старую дату
        if payment_date in original_dates:
            continue  

        # Проверяем просрочку
        if payment_date < today:
            overdue_rows.append((scooter, row))

    # Теперь проверяем новые даты переносов (scheduled_dates)
    for scooter in scooters:
        for sched_date in scheduled_dates:
            # получаем неоплаченный платёж по дате переноса
            unpaid_sched = get_postpone_for_date(scooter["id"], sched_date)
            if unpaid_sched and sched_date < today:
                # ищем платеж с этой датой в all_unpaid
                for sc, row in all_unpaid:
                    if sc["id"] == scooter["id"] and row[1] == sched_date:
                        overdue_rows.append((sc, row))

    # Очистка перед циклом для scooter и row                   
    unique = []
    seen = set()
    for scooter, row in overdue_rows:
        key = (scooter["id"], row[1])
        if key not in seen:
            seen.add(key)
            unique.append((scooter, row))

    overdue_rows = unique

    # === Если есть просрочки — отправляем их пользователю
    if overdue_rows:
        total_amount = 0
        payment_db_ids = []
        text = "⚠️ У вас есть просроченные платежи:\n\n"

        for scooter, row in overdue_rows:
            base_amount = row[2] + row[3]
            fine = 1500
            amount = base_amount + fine
            total_amount += amount
            payment_db_ids.append(row[0])
            text += (
                f"🛵 <b>{scooter['model']}</b>\n"
                f"📅 Неделя: {row[1].strftime('%d.%m.%Y')}\n"
                f"💰 Тариф: {row[2]}₽ + Штраф: {fine}₽ = <b>{amount}₽</b>\n\n"
            )

        text += (
            f"💳 <b>Итого к оплате: {total_amount}₽</b>\n\n"
            f"📌 <b>ВАЖНО:</b>\n"
            f"1️⃣ Переведите сумму на номер <b>+79000000000</b>\n"
            f"2️⃣ Отправьте <b>скриншот перевода</b> в личные сообщения заказчику: <b>@ibilsh</b>\n"
            f"3️⃣ После этого <b>обязательно нажмите кнопку «✅ Я оплатил» ниже</b>\n\n"
            f"⚠️ Без выполнения всех трёх шагов платёж <b>не будет засчитан</b>."
        )

        key = str(uuid.uuid4())[:8]
        payment_confirm_registry[key] = payment_db_ids

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f"confirm_payment:{key}")],
            [InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]
        ])
        await cleanup_lk_messages(update, context, new_text=text, reply_markup=reply_markup)
        return ConversationHandler.END

    # === 2. Переносы ===
    if active_postpones:
        total_amount = 0
        payment_db_ids = []
        text = f"🔁 Обнаружены переносы по {len(active_postpones)} скутерам:\n\n"

        for entry in active_postpones:
            scooter = entry["scooter"]
            payment = entry["payment"]
            postpone = entry["postpone"]

            amount = scooter["weekly_price"] * 2 + postpone["fine_amount"]
            total_amount += amount

            original_payment_id = payment[0]
            scheduled_payment_id = get_payment_id_by_date(scooter["id"], postpone["scheduled_date"])
            payment_db_ids.append(original_payment_id)
            if scheduled_payment_id:
                payment_db_ids.append(scheduled_payment_id)

            model = scooter["model"]
            orig = postpone["original_date"].strftime('%d.%m')
            sched = postpone["scheduled_date"].strftime('%d.%m')
            fine = postpone["fine_amount"]
            fine_text = f"⚠️ Со штрафом +{fine}₽" if fine else "✅ Без штрафа"

            text += (
                f"🛵 <b>Модель: {model}</b>\n"
                f"📅 Перенос: с <b>{orig}</b> на <b>{sched}</b>\n"
                f"💰 Сумма к оплате: <b>{amount}₽</b>\n"
                f"{fine_text}\n\n"
            )

        text += (
            f"💳 <b>Общая сумма: {total_amount}₽</b>\n\n"
            f"📌 <b>ВАЖНО:</b>\n"
            f"1️⃣ Переведите сумму на номер <b>+79000000000</b>\n"
            f"2️⃣ Отправьте <b>скриншот перевода</b> в личные сообщения заказчику: <b>@ibilsh</b>\n"
            f"3️⃣ После этого <b>обязательно нажмите кнопку «✅ Я оплатил» ниже</b>\n\n"
            f"⚠️ Без выполнения всех трёх шагов платёж <b>не будет засчитан</b>."
        )

        key = str(uuid.uuid4())[:8]
        payment_confirm_registry[key] = {
        "payment_ids": payment_db_ids,
        "postpones": active_postpones  
}

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f"confirm_payment:{key}")],
            [InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]
        ])
        await cleanup_lk_messages(update, context, new_text=text, reply_markup=reply_markup)
        return ConversationHandler.END

    # === 3. Иначе — предложить выбор недель
    context.user_data["all_unpaid"] = [row for _, row in all_unpaid]
    grouped = defaultdict(list)
    for scooter, row in all_unpaid:
        grouped[scooter["id"]].append(row)

    max_weeks = min(len(payments) for payments in grouped.values())
    if max_weeks == 0:
        await query.message.reply_text("⚠️ Недостаточно платежей для групповой оплаты.")
        return ConversationHandler.END

    await query.message.reply_text(
        f"Введите на сколько недель хотите оплатить (максимум {max_weeks}):\n\n"
        "Если вы ошиблись и не хотите сейчас оплачивать — нажмите /exit."
    )
    return ASK_WEEKS_NEW_ALL


# Обработка выбора количества недель

async def confirm_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("confirm_payment:"):
        await query.edit_message_text("❌ Неверный формат данных.")
        return

    key = data.split(":", 1)[1].strip()
    payment_info = payment_confirm_registry.get(key)

    if not payment_info:
        await query.edit_message_text("❌ Не удалось найти платежи для подтверждения.")
        return

    # Поддерживаем старый и новый форматы payment_confirm_registry
    if isinstance(payment_info, dict):
        payment_ids = payment_info.get("payment_ids", [])
    else:
        payment_ids = payment_info

    # Фильтруем платежи для обычной оплаты (amount > 0)
    payment_ids_to_mark = []
    for pid in payment_ids:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT amount FROM payments WHERE id = %s", (pid,))
                amt = cur.fetchone()[0]
                if amt > 0:
                    payment_ids_to_mark.append(pid)

    # ✅ Отмечаем платежи как оплаченные
    mark_payments_as_paid(payment_ids_to_mark)

    # ✅ Обрабатываем все платежи и закрываем переносы, если они есть
    for pid in payment_ids_to_mark:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1️⃣ Получаем данные платежа
                cur.execute("""
                    SELECT scooter_id, payment_date FROM payments WHERE id = %s
                """, (pid,))
                row = cur.fetchone()
                if not row:
                    continue
                scooter_id, payment_date = row

                # 2️⃣ Проверяем, есть ли перенос для этого платежа
                postpone_row = get_postpone_for_date(scooter_id, payment_date)
                if postpone_row:
                    original_date = postpone_row["original_date"]
                    scheduled_date = postpone_row["scheduled_date"]     

                    # ✅ Закрываем перенос
                    close_postpone(scooter_id, scheduled_date)

                    # ✅ Закрываем старый платёж (original_date): ставим is_paid=TRUE и amount=0
                    cur.execute("""
                        UPDATE payments
                        SET is_paid = TRUE, paid_at = NOW(), amount = 0
                        WHERE scooter_id = %s AND payment_date = %s
                    """, (scooter_id, original_date))

                    print(f"[DEBUG] Закрыт перенос для скутера {scooter_id}. "
                          f"original_date={original_date}, scheduled_date={scheduled_date}, "
                          f"rows affected={cur.rowcount}")

            conn.commit()

    # ✅ Удаляем ключ из реестра (завершаем обработку)
    payment_confirm_registry.pop(key, None)

    await query.edit_message_text("✅ Оплата успешно подтверждена. Спасибо!")



async def handle_weeks_count_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Пожалуйста, введите число.")
        return ASK_WEEKS_NEW_ALL

    weeks_requested = int(text)
    all_unpaid = context.user_data.get("all_unpaid", [])

    if not all_unpaid:
        await update.message.reply_text("❌ Не удалось найти платежи.")
        return ConversationHandler.END

    # Группировка по скутеру
    grouped = defaultdict(list)
    for row in all_unpaid:
        scooter_id = row[4]
        grouped[scooter_id].append(row)

    # Учитываем переносы
    scheduled_dates = set()
    original_dates = set()
    for scooter_id in grouped:
        for postpone in get_active_postpones(scooter_id):
            if isinstance(postpone, dict):
                scheduled_dates.add(postpone["scheduled_date"])
                original_dates.add(postpone["original_date"])
            elif isinstance(postpone, tuple):
                scheduled_dates.add(postpone[1])
                original_dates.add(postpone[0])

    # Фильтрация отложенных платежей
    filtered_grouped = defaultdict(list)
    for scooter_id, payments in grouped.items():
        for row in payments:
            date = row[1]
            if date in scheduled_dates or date in original_dates:
                continue
            filtered_grouped[scooter_id].append(row)

    max_weeks = min(len(payments) for payments in filtered_grouped.values())
    if weeks_requested < 1 or weeks_requested > max_weeks:
        await update.message.reply_text(f"Доступно от 1 до {max_weeks} недель. Попробуйте снова.")
        return ASK_WEEKS_NEW_ALL

    selected = []
    for i in range(weeks_requested):
        for payments in filtered_grouped.values():
            if i < len(payments):
                selected.append(payments[i])

    now = datetime.now().date()
    overdue_count = sum(1 for row in selected if row[1] < now)
    fine = overdue_count * 1500

    dates_text = "\n".join(f"📅 {row[1].strftime('%d.%m.%Y')}" for row in selected)
    total_amount = sum(row[2] + row[3] for row in selected) + fine
    payment_db_ids = [row[0] for row in selected]

    # Регистрируем оплату с ключом
    key = str(uuid.uuid4())[:8]
    payment_confirm_registry[key] = payment_db_ids

    if overdue_count > 0:
        await update.message.reply_text(
            f"⚠️ Найдено <b>{overdue_count}</b> просроченных платежей.\n"
            f"Добавлен штраф: <b>{fine}₽</b>.",
            parse_mode="HTML"
        )

    await update.message.reply_text(
        f"📦 Количество скутеров: <b>{len(filtered_grouped)}</b>\n"
        f"📅 Выбранный период: <b>{weeks_requested} нед.</b>\n"
        f"🧾 Платежей к оплате: <b>{len(selected)}</b>\n"
        f"💰 Итоговая сумма: <b>{total_amount}₽</b>\n\n"
        f"<b>Недели к оплате:</b>\n{dates_text}\n\n"
        f"📌 <b>ВАЖНО:</b>\n"
        f"1️⃣ Переведите сумму на номер <b>+79000000000</b>\n"
        f"2️⃣ Отправьте <b>скриншот перевода</b> в личные сообщения заказчику: <b>@ibilsh</b>\n"
        f"3️⃣ После этого <b>обязательно нажмите кнопку «✅ Я оплатил» ниже</b>\n\n"
        f"⚠️ Без выполнения всех трёх шагов платёж <b>не будет засчитан</b>.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Я оплатил", callback_data=f"confirm_payment:{key}")]
        ])
    )
    return ConversationHandler.END




async def handle_repair_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cleanup_lk_messages(update, context)

    tg_id = update.effective_user.id
    repairs = get_all_done_repairs(tg_id)

    if not repairs:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_silent")]
        ])
        msg = await update.callback_query.message.reply_text("🛠 История ремонтов пуста.", reply_markup=keyboard)
        context.user_data.setdefault("lk_message_ids", []).append(msg.message_id)
        return

    for created_at, problem, photo in repairs:
        date_str = created_at.strftime("%d.%m.%Y")
        caption = (
            f"📅 <b>{date_str}</b>\n"
            f"⚙ {problem}\n\n"
            f"❓ Остались вопросы по ремонту? Напишите @ibilsh"
        )

        if photo:
            msg = await context.bot.send_photo(
                chat_id=tg_id,
                photo=photo,
                caption=caption,
                parse_mode="HTML"
            )
        else:
            msg = await context.bot.send_message(
                chat_id=tg_id,
                text=caption,
                parse_mode="HTML"
            )
        
        context.user_data.setdefault("lk_message_ids", []).append(msg.message_id)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_silent")]
    ])
    msg_back = await update.callback_query.message.reply_text("↩️ Выберите действие:", reply_markup=keyboard)
    context.user_data.setdefault("lk_message_ids", []).append(msg_back.message_id)

    

async def postpone_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_client_messages(update, context)

    tg_id = update.effective_user.id
    client = get_client_by_tg_id(tg_id)
    message = update.message or update.callback_query.message

    if not client:
        msg = await message.reply_text("❗ Вы не зарегистрированы.")
        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
        return

    scooters = get_scooters_by_client(client["id"])
    if not scooters:
        msg = await message.reply_text("❗ У вас не найдено ни одного скутера.")
        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
        return

    keyboard = []
    texts = []

    for scooter in scooters:
        payments = get_unpaid_payments_by_scooter(scooter["id"])
        next_payment = payments[0] if payments else None

        if not next_payment:
            continue

        original_date = next_payment[1]
        weekly_price = next_payment[2]

        # Проверка, есть ли уже активный перенос
        active_postpones = get_active_postpones(scooter["id"])
        if active_postpones:
            scheduled_date = active_postpones[0][1]
            fine = active_postpones[0][3]
            amount = weekly_price * 2 + fine
            text = (
                f"⚠️ <b>Вы уже запрашивали перенос</b>\n\n"
                f"🛵 Модель: <b>{scooter['model']}</b>\n"
                f"🔢 VIN: <code>{scooter['vin']}</code>\n"
                f"📆 Новый срок оплаты: <b>{scheduled_date.strftime('%d.%m.%Y')}</b>\n"
                f"💰 Сумма к оплате: <b>{amount}₽</b>\n"
                f"{'⚠️ +1000₽ штраф' if fine else '✅ Без штрафа'}\n\n"
                f"Если вы оплатили — дождитесь обновления в личном кабинете."
            )
            texts.append(text)
            continue

        # Расчёт новой даты: следующая пятница
        scheduled_date = get_next_fridays(original_date + timedelta(days=1), 1)[0]

        # Определим штраф
        weekday = date.today().weekday()
        if weekday == 4:   # 4 = пятница
            fine = 1500
        elif weekday in (5, 6, 0, 1):       # суббота-вторник
            fine = 0
        else:                               # среда-четверг
            fine = 1000

        new_amount = weekly_price * 2 + fine
        if fine == 0:
            fine_text = "✅ Без штрафа"
        elif fine == 1000:
            fine_text = "⚠️ +1000₽ штраф"
        elif fine == 1500:
            fine_text = "⚠️ +1500₽ штраф (перенос на пятницу)"
        text = (
            f"⚠️ <b>Запрос на перенос платежа</b>\n\n"
            f"🛵 Модель: <b>{scooter['model']}</b>\n"
            f"🔢 VIN: <code>{scooter['vin']}</code>\n"
            f"📆 Текущий срок: <b>{original_date.strftime('%d.%m.%Y')}</b> (обнуляется)\n"
            f"📆 Новый срок: <b>{scheduled_date.strftime('%d.%m.%Y')}</b>\n"
            f"💰 Сумма к оплате: <b>{new_amount}₽</b>\n"
            f"{fine_text}\n\n"
            f"Для подтверждения нажмите кнопку 👇"
        )
        texts.append(text)

        callback_data = f"confirm_postpone:{scooter['id']}"

        context.user_data[f"postpone:{scooter['id']}"] = {
        "original_date": original_date,
        "scheduled_date": scheduled_date,
        "fine": fine
        }

        keyboard.append([
            InlineKeyboardButton(f"🛵 {scooter['model']}", callback_data=callback_data)
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    ])

    full_text = "\n\n".join(texts) if texts else "У вас нет предстоящих платежей для переноса."
    await cleanup_lk_messages(update, context, new_text=full_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def confirm_postpone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")

    scooter_id = int(data[1])
    info = context.user_data.get(f"postpone:{scooter_id}")

    if not info:
        await query.message.reply_text("❌ Данные переноса не найдены.")
        return

    original_date = info["original_date"]
    scheduled_date = info["scheduled_date"]
    fine_amount = info["fine"]
    with_fine = fine_amount > 0

    tg_id = query.from_user.id
    client = get_client_by_tg_id(tg_id)
    scooter = get_scooter_by_id(scooter_id)

    unpaid = get_unpaid_payments_by_scooter(scooter_id)
    today = date.today()

    if not unpaid:
        msg = await query.message.reply_text("✅ Нет платежей, которые можно перенести.")
        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
        return

    # Проверка на просрочки
    if any(p[1] < today for p in unpaid):
        msg = await query.message.reply_text(
            "⚠️ У вас есть просроченные платежи за предыдущие недели.\n"
            "Сначала оплатите их, чтобы оформить перенос."
        )
        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
        return

    if has_active_postpone(scooter_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ])
        msg = await query.message.reply_text(
            "⚠️ Перенос уже оформлен по этому скутеру и ещё не закрыт.\n"
            "Повторный перенос возможен только после оплаты двух недель — текущей и перенесённой.",
            reply_markup=keyboard
        )
        context.user_data.setdefault("client_message_ids", []).append(msg.message_id)
        return

    # Сохраняем запрос на перенос
    save_postpone_request(
        tg_id=tg_id,
        scooter_id=scooter_id,
        original_date=original_date,
        scheduled_date=scheduled_date,
        with_fine=with_fine,
        fine_amount=fine_amount
    )

    weekly_price = scooter["weekly_price"]
    new_amount = weekly_price * 2 + fine_amount

    # Обновляем сумму по новой дате, если платёж уже есть
    try:
        update_payment_amount(scooter_id, scheduled_date, new_amount)
    except:
        # Если платежа нет — создаём
        save_payment_schedule_by_scooter(scooter_id, [scheduled_date], new_amount)

    # Логгирование и уведомление
    log_payment_postpone(
        tg_id=tg_id,
        full_name=client["full_name"],
        phone=client["phone"],
        city=client["city"],
        original_date=original_date,
        scheduled_date=scheduled_date,
        with_fine=with_fine,
        fine_amount=fine_amount,
        vin=scooter["vin"]
    )

    await notify_admin_about_postpone(
        tg_id=tg_id,
        full_name=client["full_name"],
        original_date=original_date,
        scheduled_date=scheduled_date,
        with_fine=with_fine,
        fine_amount=fine_amount,
        vin=scooter["vin"]
    )

    text = (
        f"🔁 Перенос платежа выполнен.\n"
        f"📅 Новая дата: {scheduled_date.strftime('%d.%m.%Y')}\n"
        f"💸 {'+{}₽ штраф'.format(fine_amount) if with_fine else 'Без штрафа'}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ])

    if "main_message_id" in context.user_data:
        await cleanup_lk_messages(update, context, new_text=text, reply_markup=keyboard)
    else:
        msg = await query.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
        context.user_data["main_message_id"] = msg.message_id

async def cancel_postpone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await cleanup_lk_messages(update, context)
    await personal_account_entry(update, context)
    return ConversationHandler.END


conv_handler_pay_all = ConversationHandler(
    entry_points=[CallbackQueryHandler(handle_pay_all_entry, pattern="^pay_all$")],
    states={
        ASK_WEEKS_NEW_ALL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_weeks_count_all)],
    },
    fallbacks=[cancel_fallback, payment_back_fallback]
)

silent_back_handler = CallbackQueryHandler(handle_back_silent, pattern="^back_silent$")
postpone_conv_handler = CallbackQueryHandler(postpone_entry, pattern="^postpone$")
confirm_postpone_handler = CallbackQueryHandler(confirm_postpone, pattern="^confirm_postpone:\d+$")
confirm_payment_handler = CallbackQueryHandler(confirm_payment_callback, pattern="^confirm_payment:")
