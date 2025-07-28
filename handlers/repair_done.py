from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import ContextTypes
from database.repairs import get_repair_by_id, add_done_repair
from database.admins import get_all_admins

import os
NOTIFIER_BOT = Bot(token=os.getenv("NOTIFIER_TOKEN"))

async def confirm_repair_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    repair_id = int(query.data.split(":")[1])
    context.user_data["completed_repair_id"] = repair_id

    await query.message.reply_text(
        "💬 Прежде чем закрыть заявку, согласуйте оплату с клиентом и администратором.\n\n"
        "Когда всё подтверждено — нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить завершение", callback_data=f"confirm_done:{repair_id}")]
        ])
    )


async def finish_repair_and_notify_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    repair_id = int(query.data.split(":")[1])
    admin_ids = [a["tg_id"] for a in get_all_admins()]

    for admin_id in admin_ids:

        await NOTIFIER_BOT.send_message(
            chat_id=admin_id,
            text=f"✅ Мастер подтвердил завершение ремонта по заявке #{repair_id}. Проверьте оплату и закройте кейс.",
            parse_mode="HTML"
        )

    await query.message.reply_text("✅ Спасибо! Ремонт отмечен как завершённый.")


    repair = get_repair_by_id(repair_id)
    if repair:
        add_done_repair(repair)






