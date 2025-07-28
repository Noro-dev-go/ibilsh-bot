# admin_auth.py

from os import getenv

from telegram import Update
from telegram.ext import ContextTypes

from database.admins import is_admin, add_admin

from utils.cleanup import cleanup_admin_messages

from handlers.keyboard_utils import get_admin_inline_keyboard
from handlers.register_client import cleanup_previous_messages


async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message
    user = update.effective_user
    context.user_data["start_message_id"] = message.message_id
    await cleanup_previous_messages(update, context)

    if is_admin(user.id):
        return await show_admin_panel(update, context)

    context.user_data["awaiting_admin_pin"] = True
    await update.effective_chat.send_message("🔐 Введите PIN-код для входа в админ-панель:")


async def check_admin_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_admin_pin"):
        return

    entered_pin = update.message.text.strip()
    correct_pin = getenv("ADMIN_PIN")

    if entered_pin == correct_pin:
        user = update.effective_user
        add_admin(user.id, user.username, user.full_name)
        context.user_data.pop("awaiting_admin_pin", None)
        await update.message.reply_text("✅ Вы добавлены как админ.")
        return await show_admin_panel(update, context)
    else:
        context.user_data.pop("awaiting_admin_pin", None)
        await update.message.reply_text("❌ Неверный PIN. Доступ запрещён.")


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
