from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.validators import BAD_WORDS, compiled_bad_patterns


# Ключевые безопасные фразы из кнопок
SAFE_PHRASES = [
    "хочу электровелосипед",
    "необходим ремонт",
    "личный кабинет",
    "частые вопросы",
    "🛠 история ремонтов",
    "🛵 статус аренды",
    "💳 платежи",
    "📷 загрузить оплату",
    "📅 перенести платёж"
]

async def profanity_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return None

    text = update.message.text.strip().lower()

    if text in SAFE_PHRASES:
        return None  # кнопку пропускаем

    if any(bad in text for bad in BAD_WORDS):
        await update.message.reply_text("⛔ Без нецензурной лексики, пожалуйста.")
        return ConversationHandler.END

    if any(pattern.search(text) for pattern in compiled_bad_patterns):
        await update.message.reply_text("⛔ Просьба не использовать ненормативную лексику.")
        return ConversationHandler.END

    return None
