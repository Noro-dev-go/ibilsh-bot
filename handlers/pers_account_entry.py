from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.cleanup import cleanup_lk_messages
from handlers.admin_edit import cleanup_client_messages
from database.users import get_user_info, check_user



async def personal_account_entr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.callback_query.message
    context.user_data["start_message_id"] = message.message_id  # ✅ фиксируем ID

    #await cleanup_previous_messages(update, context)
    await cleanup_lk_messages(update, context)
    await cleanup_client_messages(update, context)

    user = update.effective_user
    tg_id = user.id

    if not check_user(tg_id):
        try:
            await message.edit_text(
                "🔒 Основной функционал личного кабинета пока недоступен.\n"
                "Вы пока не арендуете скутер через компанию Ibilsh.\n\n"
                "⚠️ Станьте частью нашей команды — и доступ к ЛК откроется!"
            )
        except:
            msg = await message.reply_text(
                "🔒 Основной функционал личного кабинета пока недоступен.\n"
                "Вы пока не арендуете скутер через компанию Ibilsh.\n\n"
                "⚠️ Станьте частью нашей команды — и доступ к ЛК откроется!"
            )
            context.user_data["lk_message_ids"].append(msg.message_id)
        return

    user_data = get_user_info(tg_id)

    text = (
        f"✅ Добро пожаловать, {user_data['full_name']}!\n"
        f"📦 Ваш статус: <b>аренда активна</b>\n\n"
        f"⚙️ Вы можете:\n"
        f"• Просмотреть основную информацию согласно вашему тарифу по аренде\n"
        f"• Просмотреть график и статус платежей\n"
        f"• Загрузить подтверждение оплаты\n"
        f"• Просмотреть историю ремонтов, обратиться к администратору при необходимости\n"
        f"• Перенести оплату на следующую неделю\n\n"
        f"<b>📌 Выберите интересующий раздел:</b>"
    )

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛵 Статус аренды", callback_data="status")],
        [InlineKeyboardButton("🛠 История ремонтов", callback_data="repairs")],
        [InlineKeyboardButton("📅 График платежей", callback_data="payments")],
        [InlineKeyboardButton("💸 Оплатить аренду", callback_data="pay_all")],
        [InlineKeyboardButton("📅 Перенести платёж", callback_data="postpone")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="client_to_main")]
    ])

    try:
        msg = await message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
        context.user_data["main_message_id"] = msg.message_id
    except Exception as e:
        # fallback — если сообщение не редактируется (например, старое)
        msg = await message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
        context.user_data["main_message_id"] = msg.message_id
