from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from database.repairs import get_repair_by_id, mark_repair_as_processed
from services.notifier import send_repair_to_master
from handlers.keyboard_utils import get_admin_inline_keyboard


MASTERS = {
    856550800: "Андрей" 
    }



async def cleanup_assign_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ids = context.user_data.get("assign_message_ids", [])
    for msg_id in ids:
        try:
            await update.effective_chat.delete_message(msg_id)
        except:
            pass
    context.user_data["assign_message_ids"] = []



async def back_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cleanup_assign_messages(update, context)
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🔧 <b>Добро пожаловать в админ-панель!</b>\n\n"
        "Здесь вы можете отслеживать заявки, оформлять клиентов, "
        "контролировать аренду и ремонт.\n"
        "Выберите действие:", reply_markup=get_admin_inline_keyboard())


async def assign_repair_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_assign_messages(update, context)

    repair_id = int(query.data.split(":")[1])
    context.user_data["repair_id"] = repair_id
    repair = get_repair_by_id(repair_id)
    context.user_data["current_repair"] = repair

    await query.message.reply_text(
        f"✅ Отлично, приступаем к заявке от <b>{repair['name']}</b> из <b>{repair['city']}</b>",
        parse_mode="HTML"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👨‍🔧 @{username}", callback_data=f"select_master:{tg_id}")]
        for tg_id, username in MASTERS.items()
    ])

    await query.message.reply_text("Выберите мастера:", reply_markup=keyboard)


async def handle_master_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await cleanup_assign_messages(update, context)

    master_id = int(query.data.split(":")[1])
    repair = context.user_data.get("current_repair")

    if not repair:
        await query.message.reply_text("⚠️ Не удалось найти данные заявки.")
        return

    try:
        await send_repair_to_master(master_id, repair)
        mark_repair_as_processed(repair["id"])
        keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в админку", callback_data="back_to_admin")]
    ])
        await query.message.reply_text("✅ Заявка успешно передана мастеру.", reply_markup=keyboard)
    except Exception as e:
        await query.message.reply_text("❌ Не удалось отправить мастеру. Убедитесь, что он начал диалог с ботом.")
