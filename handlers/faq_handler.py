from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

from handlers.cancel_handler import universal_cancel_handler

from services.faq_ai_yandex import ask_yandex_gpt

WAITING_FAQ = 1




cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|/cancel|/start|/menu|/admin)$"),
    universal_cancel_handler
)


# ⏱ Вход в режим FAQ
async def start_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data["in_faq"] = True

    text = (
        "💬 Привет еще раз! Команда разработчиков Ibilsh в тестовом формате прописала нейросеть в блок часто задаваемых вопросов.\n\n"
        "Пожалуйста, если нейросеть будет себя некорректно вести - оставьте обратную связь разработчику в телеграмм @xxxxxxxxxnxxxw\n\n"
        "Можете задать любой свой вопрос ниже, с уважением Ibilsh."
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="faq_back")]]
    message = update.callback_query.message
    sent_msg = await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Сохраняем ID сообщения для последующего удаления
    context.user_data["faq_message_id"] = sent_msg.message_id

    return WAITING_FAQ

# 🤖 Ответ от ИИ или выход
BLOCKED_TEXTS = ["Личный кабинет", "Загрузить оплату", "Перенести платёж", "Частые Вопросы"]

async def handle_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обрабатываем только если пользователь в режиме FAQ
    if not context.user_data.get("in_faq"):
        return

    user_text = update.message.text.strip()

    # Игнорируем команды и запрещённые тексты
    if user_text in BLOCKED_TEXTS or user_text.startswith("/"):
        await update.message.reply_text(
            "⚠️ Вы находитесь в режиме FAQ. Сначала нажмите «/start» или «⬅️ Назад», чтобы вернуться в главное меню."
        )
        return

    try:
        answer = ask_yandex_gpt(user_text)  # или await, если асинхронная
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text("❌ Ошибка при получении ответа. Попробуйте позже.")
        print(f"[FAQ ERROR]: {e}")



async def faq_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    faq_msg_id = context.user_data.pop("faq_message_id", None)
    if faq_msg_id:
        try:
            await update.effective_chat.delete_message(faq_msg_id)
        except:
            pass  

    context.user_data["in_faq"] = False

    try:
        await update.callback_query.message.delete()
    except:
        pass  


faq_back_handler = CallbackQueryHandler(faq_exit, pattern="^faq_back$")



faq_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_faq, pattern="^faq$")],
    states={
        WAITING_FAQ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_faq)],
    },
    fallbacks=[cancel_fallback, faq_back_handler],
)