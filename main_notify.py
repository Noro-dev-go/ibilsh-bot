import os
from dotenv import load_dotenv
from telegram.ext import Application, CallbackQueryHandler
from handlers.repair_done import confirm_repair_completion, finish_repair_and_notify_admin

load_dotenv()

# Создаём Application для второго бота
app = Application.builder().token(os.getenv("NOTIFIER_TOKEN")).build()

# Регистрируем хендлеры кнопок мастера
app.add_handler(CallbackQueryHandler(confirm_repair_completion, pattern=r"^done_repair:\d+$"))
app.add_handler(CallbackQueryHandler(finish_repair_and_notify_admin, pattern=r"^confirm_done:\d+$"))

if __name__ == "__main__":
    print("✅ Notifier bot запущен и слушает callback-кнопки...")
    app.run_polling()
