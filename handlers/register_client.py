from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler

from services.notifier import notify_admin_about_new_client
from handlers.cancel_handler import universal_cancel_handler
from database.db import get_connection
from database.pending import save_pending_user
from utils.validators import is_valid_name
from handlers.keyboard_utils import get_keyboard

ASK_NAME, ASK_AGE, ASK_CITY, ASK_PHONE, ASK_TARIFF, CONFIRM_ORDER, ASK_SHOW_PRODUCTS = range(7)

cancel_fallback = MessageHandler(
    filters.Regex("^(⬅️ Назад|назад|отмена|/cancel|/start|/menu)$"),
    universal_cancel_handler
)

# === Вспомогательные функции для очистки ===
async def cleanup_previous_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
   if "start_message_id" in context.user_data:
        try:
            await update.effective_chat.delete_message(context.user_data["start_message_id"])
        except:
           pass
        del context.user_data["start_message_id"]

        if "cleanup_messages" in context.user_data:
            for msg_id in context.user_data["cleanup_messages"]:
                try:
                    await update.effective_chat.delete_message(msg_id)
                except:
                    pass
            context.user_data["cleanup_messages"].clear()
        else:
            context.user_data["cleanup_messages"] = []

def store_message_id(context, message):
    context.user_data.setdefault("cleanup_messages", []).append(message.message_id)


# === Хендлеры ===
async def entry_point_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message
    await cleanup_previous_messages(update, context)
    
    context.user_data["start_message_id"] = message.message_id

    msg = await message.reply_text(
        "<b>📄 У нас для тебя есть несколько вариантов:</b>\n\n"
        "🔋 <b>Аренда с одним аккумулятором</b>: 2000₽ в неделю\n"
        "🔋 <b>Аренда с двумя аккумуляторами</b>: 3000₽ в неделю\n"
        "📦 <b>Выкуп</b>: 3000₽/нед. ~50 недель\n\n"
        "⚡ <b>Напоминаем:</b> никаких залогов и предоплат!\n"
        "Первая оплата назначается через неделю после получения.",
        parse_mode="HTML"
    )
    store_message_id(context, msg)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да", callback_data="show_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="show_no")
        ]
    ])
    msg2 = await message.reply_text("Хотите посмотреть наш ассортимент?", reply_markup=keyboard)
    store_message_id(context, msg2)
    return ASK_SHOW_PRODUCTS

async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await cleanup_previous_messages(update, context)

    if query.data == "show_yes":
        photo_msg = await query.message.reply_photo(
            photo=open("images/syccyba_one_ACB.jpg", "rb"),
            caption=(
                "🛵 <b>Syccoba (электровелосипед)</b>\n\n"
                "🔋 Аккумулятор: 60V, 21Ah\n"
                "⚡ Скорость до: 25 км/ч\n"
                "🚗 Запас хода до: 70 км\n"
                "🏍 Мощность двигателя: 240/1000 Вт\n"
                "🛞 Колёса: 16\" бескамерные\n"
                "⏱ Время зарядки: ~7 ч\n"
                "🧍‍♂️ Макс. нагрузка: 150 кг\n"
                "📟 Дисплей, амортизация, съёмная батарея, гидротормоза\n"
                "📦 Размер: 170×115×80 см, Вес: 57.5 кг"
            ),
            parse_mode="HTML"
        )
        store_message_id(context, photo_msg)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да", callback_data="yes"),
                InlineKeyboardButton("❌ Нет", callback_data="no")
            ]
        ])
        msg = await query.message.reply_text("Хотите оформить заявку?", reply_markup=keyboard)
        context.user_data["start_message_id"] = query.message.message_id
        store_message_id(context, msg)
        return CONFIRM_ORDER
    else:
        await cleanup_previous_messages(update, context)
        await query.message.reply_text("⚡ Приветствую, дорогой друг! Это бот компании Ibilsh — твоего помощника в мире электровелосипедов!\n\n"
        "🔹 Хочешь к нам в команду? — Оформим заявку на твой новенький электровело в пару кликов!\n"
        "🔹 Что-то сломалось? — Мастер будет у тебя через несколько часов!\n"
        "🔹 Уже с нами? — Загляни в личный кабинет!\n"
        "🔹 Появились вопросы? — Мы собрали часто задаваемые вопросы и ответы на них!\n\n"
        "👇 Выбери, что тебе нужно:", reply_markup=get_keyboard())
        return ConversationHandler.END

async def already_pending(tg_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pending_users WHERE tg_id = %s AND is_processed = FALSE", (tg_id,))
            return cur.fetchone() is not None

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["start_message_id"] = query.message.message_id
    await cleanup_previous_messages(update, context)

    tg_id = query.from_user.id
    if await already_pending(tg_id):
        msg = await query.message.reply_text(
            "⚠️ Ваша заявка уже находится на рассмотрении.\nПожалуйста, дождитесь ответа администратора.",
            reply_markup=get_keyboard()
        )
        store_message_id(context, msg)
        return ConversationHandler.END

    if query.data == "yes":
        msg = await query.message.reply_text("🌐 Отлично! Давайте начнём. Как вас зовут?", reply_markup=ReplyKeyboardRemove())
        store_message_id(context, msg)
        return ASK_NAME
    else:
        msg = await query.message.reply_text("⚡ Приветствую, дорогой друг! Это бот компании Ibilsh — твоего помощника в мире электровелосипедов!\n\n"
        "🔹 Хочешь к нам в команду? — Оформим заявку на твой новенький электровело в пару кликов!\n"
        "🔹 Что-то сломалось? — Мастер будет у тебя через несколько часов!\n"
        "🔹 Уже с нами? — Загляни в личный кабинет!\n"
        "🔹 Появились вопросы? — Мы собрали часто задаваемые вопросы и ответы на них!\n\n"
        "👇 Выбери, что тебе нужно:", reply_markup=get_keyboard())
        context.user_data["start_message_id"] = query.message.message_id
        store_message_id(context, msg)
        return ConversationHandler.END

async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_previous_messages(update, context)
    name = update.message.text.strip()
    if not is_valid_name(name):
        msg = await update.message.reply_text("❗ Пожалуйста, введите корректное имя (только буквы и пробелы, без мата).")
        store_message_id(context, msg)
        return ASK_NAME

    context.user_data["name"] = name
    msg = await update.message.reply_text("🌐 Сколько вам лет?")
    store_message_id(context, msg)
    return ASK_AGE

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_previous_messages(update, context)
    age = update.message.text.strip()
    if not age.isdigit() or not (18 <= int(age) <= 65):
        msg = await update.message.reply_text("❗ Мы не можем выдать под аренду электровелосипед лицам младше 18-ти лет.")
        store_message_id(context, msg)
        return ASK_AGE

    context.user_data["age"] = age
    msg = await update.message.reply_text("📍 В каком городе вы находитесь?")
    store_message_id(context, msg)
    return ASK_CITY

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_previous_messages(update, context)
    context.user_data["city"] = update.message.text.strip()
    msg = await update.message.reply_text("📞 Укажите ваш номер телефона:")
    store_message_id(context, msg)
    return ASK_PHONE

async def ask_tariff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_previous_messages(update, context)
    phone = update.message.text.strip()
    context.user_data["phone"] = phone
    if not phone.isdigit() or len(phone) != 11:
        msg = await update.message.reply_text("❗ Пожалуйста, введите корректный номер из 11 цифр, начиная с 7:")
        store_message_id(context, msg)
        return ASK_PHONE

    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("1 АКБ — 2000₽")],
        [KeyboardButton("2 АКБ — 3000₽")],
        [KeyboardButton("Выкуп — 3000₽ / ~50 недель")]
    ], resize_keyboard=True)

    msg = await update.message.reply_text("💼 Какой тариф вас интересует?", reply_markup=keyboard)
    store_message_id(context, msg)
    return ASK_TARIFF


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_previous_messages(update, context)

    context.user_data["preferred_tariff"] = update.message.text.strip()

    # ✅ Убираем клавиатуру сразу, не дожидаясь конца FSM
    await update.message.reply_text("Все необходимые данные получены, спасибо! Ожидайте, мы скоро с вами свяжемся.", reply_markup=ReplyKeyboardRemove())

    tg_user = update.effective_user
    context.user_data["username"] = f"@{tg_user.username}" if tg_user.username else "не указан"
    context.user_data["tg_id"] = tg_user.id

    data = context.user_data
    save_pending_user(data)

    try:
        await notify_admin_about_new_client(data)
    except Exception as e:
        print(f"[ERROR] Уведомление админу не отправлено: {e}")

    await update.message.reply_text("🔙 Вы вернулись в главное меню.", reply_markup=get_keyboard())
    return ConversationHandler.END


register_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(entry_point_button, pattern="^rent$")],
    states={
        ASK_SHOW_PRODUCTS: [CallbackQueryHandler(show_products)],
        CONFIRM_ORDER: [CallbackQueryHandler(confirm_order)],
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
        ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_city)],
        ASK_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tariff)],
        ASK_TARIFF: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish)],
       
    },
    fallbacks=[cancel_fallback]
)
