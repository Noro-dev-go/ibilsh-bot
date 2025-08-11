# admin_auth.py

from os import getenv

from telegram import Bot, Update
from telegram.ext import ContextTypes

from database.admins import add_admin

from database.admin_security import (
    get_security_state, set_lock, clear_lock_and_attempts,
    increment_attempt, is_locked, get_last_attempt_at
)

from utils.cleanup import cleanup_admin_messages

from datetime import datetime, timedelta, timezone

from handlers.keyboard_utils import get_admin_inline_keyboard
from handlers.register_client import cleanup_previous_messages



NOTIFIER_BOT = Bot(token=getenv("NOTIFIER_TOKEN"))
ADMIN_ALERT_TG_ID = int(getenv("OWNER_TG_ID"))


MAX_ATTEMPTS = int(getenv("ADMIN_MAX_ATTEMPTS", 3))
LOCK_MINUTES = int(getenv("ADMIN_LOCK_MINUTES", 480))
RATE_LIMIT_SECONDS = int(getenv("ADMIN_RATE_LIMIT_SECONDS", 2))


def _remain_text(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    sec = max(int((dt - now).total_seconds()), 0)
    m, s = divmod(sec, 60)
    return f"{m} мин {s} сек" if m else f"{s} сек"



async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_previous_messages(update, context)

    user = update.effective_user
    locked_until = is_locked(user.id)
    if locked_until and datetime.now(timezone.utc) < locked_until:
        await update.effective_chat.send_message(
            f"⛔ Доступ заблокирован. Подождите {_remain_text(locked_until)}."
        )
        return

    if context.user_data.get("admin_authenticated"):
        return await show_admin_panel(update, context)

    context.user_data["awaiting_admin_pin"] = True
    await update.effective_chat.send_message("🔐 Введите PIN-код для входа в админ-панель:")



async def check_admin_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_admin_pin"):
        return

    user = update.effective_user

    # 1) Проверка блокировки
    locked_until = is_locked(user.id)
    if locked_until and datetime.now(timezone.utc) < locked_until:
        await update.message.reply_text(f"⛔ Доступ заблокирован. Подождите {_remain_text(locked_until)}.")
        context.user_data.pop("awaiting_admin_pin", None)
        return

    # 2) Антифлуд (частота)
    last_at = get_last_attempt_at(user.id)
    if last_at and (datetime.now(timezone.utc) - last_at).total_seconds() < RATE_LIMIT_SECONDS:
        await update.message.reply_text("⏳ Слишком часто. Подождите пару секунд и попробуйте снова.")
        return

    entered_pin = update.message.text.strip()
    correct_pin = getenv("ADMIN_PIN")

    if entered_pin == correct_pin:
        add_admin(user.id, user.username, user.full_name)
        context.user_data["admin_authenticated"] = True
        context.user_data.pop("awaiting_admin_pin", None)
        clear_lock_and_attempts(user.id)
        await update.message.reply_text("✅ PIN верный, доступ разрешён.")
        return await show_admin_panel(update, context)

    # Неверно — инкремент в БД
    attempts = increment_attempt(user.id)

    if attempts >= MAX_ATTEMPTS:
        lock_until = set_lock(user.id, LOCK_MINUTES)
        alert_text = (
            f"🚨 <b>{MAX_ATTEMPTS} неверные попытки входа в админку!</b>\n\n"
            f"👤 {user.full_name} | @{user.username or '—'}\n"
            f"🆔 <code>{user.id}</code>\n"
            f"⏱ Блок до: <code>{lock_until.isoformat(timespec='seconds')}</code>"
        )
        await NOTIFIER_BOT.send_message(ADMIN_ALERT_TG_ID, alert_text, parse_mode="HTML")
        context.user_data.pop("awaiting_admin_pin", None)
        await update.message.reply_text(
            f"⛔ Превышено число попыток. Доступ заблокирован на {_remain_text(lock_until)}."
        )
        return

    left = MAX_ATTEMPTS - attempts
    await update.message.reply_text(f"❌ Неверный PIN. Осталось попыток: {left}")


async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("came_from_search", None)
    context.user_data.pop("client_id", None)
    await cleanup_admin_messages(update, context)

    text = (
        "🔧 <b>Добро пожаловать в админ-панель!</b>\n\n"
        "Здесь вы можете отслеживать заявки, оформлять клиентов, "
        "контролировать аренду и ремонт.\n"
        "Выберите действие:"
    )

    msg = await update.effective_chat.send_message(
        text,
        reply_markup=get_admin_inline_keyboard(),
        parse_mode="HTML"
    )

    context.user_data.setdefault("admin_message_ids", []).append(msg.message_id)
