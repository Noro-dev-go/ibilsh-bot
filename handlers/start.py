from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler
from handlers.keyboard_utils import get_keyboard 
from database.tg_users import save_basic_user, user_exists


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    # ✅ сохраняем tg_id и username
    user = update.effective_user
    tg_id = user.id
    username = f"@{user.username}" if user.username else None
    print(f"[START] tg_id: {tg_id}, username: {username}")

    # ✅ проверяем, есть ли уже этот tg_id в базе
    if not user_exists(tg_id):
        save_basic_user(tg_id, username)
        print("[START] Пользователь сохранен в базу")
    else:
        print("[START] Пользователь уже существует, сохранение не требуется")

    msg = await update.message.reply_text(
        "⚡ Приветствую, дорогой друг! Это бот компании Ibilsh — твоего помощника в мире электровелосипедов!\n\n"
        "🔹 Хочешь к нам в команду? — Оформим заявку на твой новенький электровело в пару кликов!\n"
        "🔹 Что-то сломалось? — Мастер будет у тебя через несколько часов!\n"
        "🔹 Уже с нами? — Загляни в личный кабинет!\n"
        "🔹 Появились вопросы? — Мы собрали часто задаваемые вопросы и ответы на них!\n\n"
        "👇 Выбери, что тебе нужно:",
        reply_markup=get_keyboard()
    )
    context.user_data["start_message_id"] = msg.message_id
    return ConversationHandler.END


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📋 Главное меню:", reply_markup=get_keyboard())
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "🆘 <b>Что делать, если бот не отвечает?</b>\n\n"
        "1️⃣ Нажмите кнопку <b>Меню</b> снизу, чтобы открыть команды.\n"
        "2️⃣ Или введите /start для перезапуска.\n"
        "3️⃣ Убедитесь, что у вас стабильный интернет.\n\n"
        "🆘 <b>Что делать, если бот завис, присылает непонятные сообщения об ошибках?</b>\n\n" \
        "Для того чтобы выйти из состояния, когда бот присылает одно и тоже сообщение в ответ на ваши действия - пропишите команду /start, в большинстве случаев это поможет выйти из зависания.\n\n"
        "Если ничего не помогает — напишите администратору, его тэг @xxxxxxxxxnxxxw",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Владелец - @ibilsh\n" \
        "Разработчик бота - @tolstovdev\n\n" \
        "Если у Вас возник вопрос по поводу работы бота Ibilsh или какая-либо идея по улучшению функционала, то смело пишите разработчику\n\n" \
        "Если же у Вас вопрос, касающийся непосредственно аренды\выкупа электровелосипеда, то пишите владельцу.",
        parse_mode="HTML"
    )
    return ConversationHandler.END



start_handler = CommandHandler("start", start)
menu_handler = CommandHandler("menu", menu_command)
help_handler = CommandHandler("help", help_command)
contact_handler = CommandHandler("contacts", contact_command)
