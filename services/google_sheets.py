import os
import gspread
from datetime import datetime, date
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

# === Настройки ===
SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
CREDS_PATH = "credentials/google/ibilshbot-7c4d1bbce9ea.json"
BOT_TOKEN = os.getenv("BOT_TOKEN")

# === Авторизация Google Sheets ===
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1  # первая вкладка

bot = Bot(token=BOT_TOKEN)


async def append_payment_row(tg_id: int, username: str, dates: list, weeks_count: int, photo_file_id: str):
    """
    Добавляет строку в Google Таблицу.
    :param tg_id: Telegram ID клиента
    :param username: username клиента (с @ или 'не указан')
    :param dates: список строк дат вида 14.06.2025
    :param weeks_count: кол-во недель оплаты
    :param photo_file_id: file_id Telegram-снимка
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        file = await bot.get_file(photo_file_id)
        file_url = file.file_path
    except Exception as e:
        file_url = f"Ошибка получения URL: {e}"

    sheet.append_row([
        str(tg_id),
        username,
        now,
        ", ".join(dates),
        str(weeks_count),
        file_url
    ])

def log_payment_postpone(
    tg_id: int,
    full_name: str,
    phone: str,
    city: str,
    original_date: date,
    scheduled_date: date,
    with_fine: bool,
    fine_amount: int,
    vin: str
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fine_text = f"⚠️ Штраф +{fine_amount}₽" if with_fine else "✅ Без штрафа"

    sheet.append_row([
        str(tg_id),
        full_name,
        phone,
        city,
        vin,
        original_date.strftime("%d.%m.%Y"),
        scheduled_date.strftime("%d.%m.%Y"),
        now,
        fine_text
    ])