# wash_reminder.py
from __future__ import annotations

import io
import os
from datetime import datetime, timedelta, time
from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# === DB ===
from database.users import get_renters_tg_ids

# === Google Drive (сервисный аккаунт) ===
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from services.google_drive import user_drive_service

from dotenv import load_dotenv

MAX_PHOTOS = 4
AWAIT_PHOTOS = 1

def _env():
    # безопасно вызывается много раз; вернёт значения актуально на момент вызова
    load_dotenv()
    google_sa = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_SA_JSON")
    folder_id = os.getenv("WASH_DRIVE_FOLDER_ID")
    return google_sa, folder_id


# =========================
# 1) Напоминание с кнопкой
# =========================
async def send_wash_reminders(bot):
    """
    Рассылаем напоминание клиентам с кнопкой, которая запускает загрузку фото мойки.
    """
    text = (
        "🧼 Привет! Напоминание: раз в две недели нужно помыть скутер.\n\n"
        "Пожалуйста, помойте его сегодня и отправьте сюда 4 фото (можно одним альбомом)."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Загрузить фото мойки", callback_data="wash_upload")]
    ])

    tg_ids = get_renters_tg_ids()
    for tg_id in tg_ids:
        try:
            await bot.send_message(chat_id=tg_id, text=text, reply_markup=keyboard)
        except Exception as e:
            print(f"[wash_reminder] failed to send to {tg_id}: {e}")


def next_friday_15():
    """
    Возвращает ближайшую пятницу 15:00 (локальное время сервера).
    """
    now = datetime.now()
    days_ahead = (4 - now.weekday()) % 7  # пятница = 4
    candidate_date = (now + timedelta(days=days_ahead)).date()
    candidate_dt = datetime.combine(candidate_date, time(15, 0))
    if candidate_dt <= now:
        candidate_dt += timedelta(weeks=1)
    return candidate_dt


# =========================================
# 2) Хелперы для Google Drive (сервис-акк)
# =========================================
def _drive_service():
    return user_drive_service()


def _find_or_create_subfolder(service, parent_id: str, name: str) -> str:
    # ищем подпапку с таким именем
    query = (
        f"mimeType='application/vnd.google-apps.folder' and name='{name}' "
        f"and '{parent_id}' in parents and trashed=false"
    )
    res = service.files().list(q=query, spaces="drive", fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    # создаём подпапку
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    folder = service.files().create(body=body, fields="id").execute()
    return folder["id"]


def _upload_jpeg_bytes(service, folder_id: str, filename: str, data: bytes):
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="image/jpeg", resumable=False)
    body = {"name": filename, "parents": [folder_id]}
    service.files().create(body=body, media_body=media, fields="id").execute()


# ======================================================
# 3) FSM: запуск приёма фото + сбор до 4 шт + выгрузка
# ======================================================
async def start_wash_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Старт сценария загрузки фото после нажатия инлайн-кнопки.
    """
    query = update.callback_query
    await query.answer()

    # обнуляем пачку
    context.user_data["wash_pack"] = {
        "photos": [],           # list[file_id]
        "media_group_id": None  # чтобы собрать альбом
    }

    text = (
        "🧼 Ок! Пришлите *4 фото мойки*.\n\n"
        "Можно *одним альбомом* (до 10 фото) или по одной — я засчитаю первые 4.\n"
        "Когда загрузите, отправлю их администратору :)"
    )
    await query.message.edit_text(text, parse_mode="Markdown")
    return AWAIT_PHOTOS


async def collect_wash_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Принимаем фото, учитываем альбом по media_group_id, набираем до 4 штук.
    Как только набрали — грузим на Drive и выходим из сценария.
    """
    msg = update.message
    if not msg or not msg.photo:
        return AWAIT_PHOTOS

    file_id = msg.photo[-1].file_id
    pack = context.user_data.get("wash_pack", {"photos": [], "media_group_id": None})

    # Если это альбом — фиксируем и пускаем только кадры из него
    if msg.media_group_id:
        if pack["media_group_id"] is None:
            pack["media_group_id"] = msg.media_group_id
        if pack["media_group_id"] != msg.media_group_id:
            # игнорируем чужой альбом, пока не добили текущий
            return AWAIT_PHOTOS

    if len(pack["photos"]) < MAX_PHOTOS:
        pack["photos"].append(file_id)
        context.user_data["wash_pack"] = pack

    if len(pack["photos"]) >= MAX_PHOTOS:
        await msg.reply_text("Загружаю фото на Google Drive…")
        try:
            await _upload_pack_to_drive(update, context, pack["photos"])
            await msg.reply_text("✅ Готово! Фото сохранены на Google Drive.")
        except Exception as e:
            await msg.reply_text(f"❌ Ошибка загрузки на Google Drive: {e}")
        finally:
            context.user_data.pop("wash_pack", None)
        return ConversationHandler.END

    remain = MAX_PHOTOS - len(pack["photos"])
    await msg.reply_text(f"Принято {MAX_PHOTOS - remain}/{MAX_PHOTOS}. Дошлите ещё {remain} фото.")
    return AWAIT_PHOTOS


async def _upload_pack_to_drive(update, context, file_ids):
    user = update.effective_user
    username = (user.username and f"@{user.username}") or None
    owner_tag = username or str(user.id)
    today = datetime.now().date().isoformat()

    service = _drive_service()
    _, wash_folder_id = _env()  # ← получаем актуальный ID папки
    subfolder = f"{today}__{owner_tag}"
    pack_folder_id = _find_or_create_subfolder(service, wash_folder_id, subfolder)

    for idx, fid in enumerate(file_ids[:MAX_PHOTOS], start=1):
        tg_file = await context.bot.get_file(fid)
        buff = io.BytesIO()
        await tg_file.download_to_memory(out=buff)
        buff.seek(0)
        filename = f"{today}__{owner_tag}__{idx}.jpg"
        _upload_jpeg_bytes(service, pack_folder_id, filename, buff.getvalue())



# ==========================================================
# 4) Конструктор ConversationHandler для подключения в app
# ==========================================================
def build_wash_conversation_handler() -> ConversationHandler:
    """
    Добавь в Application:  application.add_handler(build_wash_conversation_handler())
    """
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_wash_upload, pattern="^wash_upload$")],
        states={
            AWAIT_PHOTOS: [MessageHandler(filters.PHOTO, collect_wash_photos)],
        },
        fallbacks=[],
        per_message=False,
    )
