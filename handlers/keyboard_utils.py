from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🚴 Хочу электровелосипед", callback_data="rent"),
            InlineKeyboardButton("🔧 Необходим ремонт", callback_data="repair")
        ],
        [
            InlineKeyboardButton("👤 Личный кабинет", callback_data="personal_account"),
            InlineKeyboardButton("❓ Частые вопросы", callback_data="faq")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Необработанные заявки", callback_data="admin_pending")],
        [InlineKeyboardButton("🔧 Необработанные заявки (ремонт)", callback_data="admin_pending_repairs")],
        [InlineKeyboardButton("👥 Все клиенты", callback_data="admin_all_clients")],
        [InlineKeyboardButton("🔎 Поиск клиента", callback_data="admin_search")],
        [InlineKeyboardButton("✅ Все выполненные ремонты", callback_data="admin_done_repairs")],
        [InlineKeyboardButton("💸 Неоплаченные платежи", callback_data="unpaid_payments")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="admin_to_main")]
    ]) 