import os
import asyncio
import nest_asyncio
from dotenv import load_dotenv


from handlers.start import start_handler, menu_handler, help_handler, contact_handler

from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.notify_utils import send_payment_notifications_with_button
from utils.bot_commands import setup_bot_commands

# Хендлеры пользователей
from handlers.start import start
from handlers.faq_handler import start_faq,  faq_back_handler, faq_conv_handler
from handlers.personal_account import (
    personal_account_entry, back_to_personal_menu, exit_to_personal_menu,
    handle_status, handle_repair_history, handle_payments, go_to_main_menu,
    conv_handler_pay_all, postpone_conv_handler, confirm_postpone_handler, silent_back_handler, confirm_payment_handler
)
from handlers.repair_request import (
    repair_conv_handler, short_repair_conv_handler,
    repair_entry_handler, repair_back_handler
)

# Хендлеры админки
from handlers.register_client import register_conv_handler
from handlers.admin_register import admin_register_conv_handler, register_admin_reg_handlers
from handlers.admin_edit import start_edit_client, edit_conv_handler
from handlers.admin_panel import register_admin_handlers
from handlers.admin_assign import assign_repair_callback, handle_master_selection, back_to_admin


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # --- Пользовательские FSM и хендлеры ---
    app.add_handler(faq_conv_handler)
    app.add_handler(MessageHandler(filters.Regex("^⬅️ Назад$"), start))
    app.add_handler(CallbackQueryHandler(personal_account_entry, pattern="^personal_account$"))
    app.add_handler(CallbackQueryHandler(back_to_personal_menu, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(go_to_main_menu, pattern="^client_to_main$"))
    app.add_handler(CallbackQueryHandler(start_faq, pattern="^faq$"))
    app.add_handler(faq_back_handler)
    app.add_handler(CallbackQueryHandler(handle_status, pattern="^status$"))
    app.add_handler(CallbackQueryHandler(handle_repair_history, pattern="^repairs$"))
    app.add_handler(CallbackQueryHandler(handle_payments, pattern="^payments$"))
    app.add_handler(silent_back_handler)
    app.add_handler(conv_handler_pay_all)
    app.add_handler(postpone_conv_handler)
    app.add_handler(confirm_postpone_handler)
    app.add_handler(confirm_payment_handler)

    # --- Хендлеры регистрации и ремонта ---
    app.add_handler(register_conv_handler)
    app.add_handler(repair_conv_handler)
    app.add_handler(short_repair_conv_handler)
    app.add_handler(repair_entry_handler)
    app.add_handler(repair_back_handler)

    # --- Админка ---
    app.add_handler(CallbackQueryHandler(start_edit_client, pattern=r"^edit_client:\d+$"))
    app.add_handler(admin_register_conv_handler)
    app.add_handler(edit_conv_handler)
    register_admin_handlers(app)
    register_admin_reg_handlers(app)
    app.add_handler(CallbackQueryHandler(assign_repair_callback, pattern=r"^assign_repair:\d+$"))
    app.add_handler(CallbackQueryHandler(handle_master_selection, pattern=r"^select_master:\d+$"))
    app.add_handler(CallbackQueryHandler(back_to_admin, pattern="^back_to_admin$"))

    # --- Команды ---
    
    app.add_handler(start_handler)
    app.add_handler(menu_handler)
    app.add_handler(help_handler)
    app.add_handler(contact_handler)

    # --- Команды Telegram /start, /help и т.д. ---
    await setup_bot_commands(app.bot)
    
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^/exit$"), exit_to_personal_menu))

    print("Бот запущен...")

    # --- Планировщик уведомлений ---
    scheduler = AsyncIOScheduler()

# Уведомления при просрочке (раз в 60 минут)
    scheduler.add_job(
    send_payment_notifications_with_button,
    "interval",
    minutes=25,
    kwargs={"bot": app.bot, "severity": "overdue"}
)

# Стандартные уведомления в 8:00, 12:00, 16:00, 20:00
    times = [(8, 0), (12, 0), (16, 0), (16, 53), (20, 0)]

    for hour, minute in times:
        scheduler.add_job(
            send_payment_notifications_with_button,
            "cron",
        hour=hour,
        minute = minute,
        kwargs={"bot": app.bot, "severity": "standard"}
    )

# Запуск планировщика
    scheduler.start()
    await app.run_polling()


if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
