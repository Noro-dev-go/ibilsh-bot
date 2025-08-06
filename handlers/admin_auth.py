# admin_auth.py

from os import getenv

from telegram import Bot, Update
from telegram.ext import ContextTypes

from database.admins import is_admin, add_admin
from utils.cleanup import cleanup_admin_messages

from handlers.keyboard_utils import get_admin_inline_keyboard
from handlers.register_client import cleanup_previous_messages

NOTIFIER_BOT = Bot(token=getenv("NOTIFIER_TOKEN"))
ADMIN_ALERT_TG_ID = int(getenv("OWNER_TG_ID"))

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message
    await cleanup_previous_messages(update, context)

    # Если уже ввёл PIN в этой сессии — просто заходим
    if context.user_data.get("admin_authenticated"):
        return await show_admin_panel(update, context)

    # Иначе спрашиваем PIN
    context.user_data["awaiting_admin_pin"] = True
    context.user_data.setdefault("admin_pin_attempts", 0)
    await update.effective_chat.send_message("🔐 Введите PIN-код для входа в админ-панель:")


async def check_admin_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_admin_pin"):
        return

    entered_pin = update.message.text.strip()
    correct_pin = getenv("ADMIN_PIN")

    if entered_pin == correct_pin:
        user = update.effective_user
        add_admin(user.id, user.username, user.full_name)

        # Отмечаем, что админ авторизован на сессию
        context.user_data["admin_authenticated"] = True
        context.user_data["admin_pin_attempts"] = 0
        context.user_data.pop("awaiting_admin_pin", None)

        await update.message.reply_text("✅ PIN верный, доступ разрешён.")
        return await show_admin_panel(update, context)

    # Неверный PIN
    context.user_data["admin_pin_attempts"] += 1
    attempts = context.user_data["admin_pin_attempts"]

    if attempts >= 3:
        user = update.effective_user
        context.user_data.pop("awaiting_admin_pin", None)
        context.user_data["admin_pin_attempts"] = 0

        alert_text = (
            f"🚨 <b>3 неверные попытки входа в админку!</b>\n\n"
            f"👤 {user.full_name} | @{user.username or '—'}\n"
            f"🆔 <code>{user.id}</code>"
        )
        await NOTIFIER_BOT.send_message(
            chat_id=ADMIN_ALERT_TG_ID,
            text=alert_text,
            parse_mode="HTML"
        )

        await update.message.reply_text("⛔ Вы превысили количество попыток. Доступ временно заблокирован.")
        return

    await update.message.reply_text(f"❌ Неверный PIN. Осталось попыток: {3 - attempts}")
    
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
