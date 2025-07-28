from telegram import BotCommand

async def setup_bot_commands(bot):
    await bot.set_my_commands([
        BotCommand("start", "Перезапустить бота"),
        BotCommand("menu", "Вернуться в меню"),
        BotCommand("help", "Помощь при зависании")
    ])
