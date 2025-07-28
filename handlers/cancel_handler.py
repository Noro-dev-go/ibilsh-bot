from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from handlers.keyboard_utils import get_keyboard, get_admin_inline_keyboard



# Все ключевые слова выхода из FSM
CANCEL_KEYWORDS = ["/cancel", "назад", "отмена", "⬅️ назад", "/start", "/menu", "/admin", "/back"]

async def universal_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["in_faq"] = False  

 
    faq_msg_id = context.user_data.pop("faq_message_id", None)
    if faq_msg_id:
        try:
            await update.effective_chat.delete_message(faq_msg_id)
        except:
            pass

    await update.message.reply_text("🔙 Возврат в главное меню", reply_markup=get_keyboard())
    return ConversationHandler.END


async def admin_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
 
    for key in ["edit_message_ids", "client_message_ids"]:
        for msg_id in context.user_data.get(key, []):
            try:
                await update.effective_chat.delete_message(msg_id)
            except:
                pass
        context.user_data[key] = []

    await update.message.reply_text("🔙 Возврат в админ-панель", reply_markup=get_admin_inline_keyboard())
    return ConversationHandler.END



async def exit_lk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.pers_account_entry import personal_account_entr 
    # Очистка сообщений, связанных с ЛК (фото, меню, и т.д.)
    for key in ["lk_message_ids"]:
        for msg_id in context.user_data.get(key, []):
            try:
                await update.effective_chat.delete_message(msg_id)
            except:
                pass
        context.user_data[key] = []

    # Можно также обнулить главное сообщение, если нужно:
    context.user_data.pop("main_message_id", None)

    # Возврат в главное меню ЛК
    await update.message.reply_text("🔙 Возврат в личный кабинет")
    await personal_account_entr(update, context)

    return ConversationHandler.END