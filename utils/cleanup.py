from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest


async def cleanup_admin_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, key="admin_message_ids"):
    if key not in context.user_data:
        context.user_data[key] = []
        return

    for msg_id in context.user_data[key]:
        try:
            await update.effective_chat.delete_message(msg_id)
        except Exception as e:
            print(f"[cleanup_admin_messages] Не удалось удалить сообщение {msg_id}: {e}")
    
    context.user_data[key] = []


async def cleanup_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_id = context.user_data.pop("welcome_msg_id", None)
    if msg_id:
        try:
            await update.effective_chat.delete_message(msg_id)
        except:
            pass


async def cleanup_lk_messages(update: Update, context: ContextTypes.DEFAULT_TYPE, new_text: str = None, reply_markup=None):
    """Удаляет временные сообщения и при необходимости редактирует или отправляет главное сообщение."""

    # Удаление всех временных сообщений
    for msg_id in context.user_data.get("lk_message_ids", []):
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception as e:
            print(f"[DEBUG] ❌ Не удалось удалить сообщение {msg_id}: {e}")
    context.user_data["lk_message_ids"] = []

    msg_id = context.user_data.get("main_message_id")
    if not msg_id or not new_text:
        return

    try:
        if update.callback_query:
            # inline-контекст — редактируем
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg_id,
                text=new_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        else:
            # обычный текстовый вызов — отправляем новое сообщение
            msg = await update.message.reply_text(
                new_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            # Сохраняем новый main_message_id
            context.user_data["main_message_id"] = msg.message_id

    except BadRequest as e:
        if "Message is not modified" in str(e):
            return        