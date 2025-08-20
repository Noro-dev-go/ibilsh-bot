import os
import aiofiles
import aiohttp
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.error import TelegramError

from database.users import get_user_info
from database.admins import get_all_admins


load_dotenv()

NOTIFIER_BOT = Bot(token=os.getenv("NOTIFIER_TOKEN"))
MAIN_BOT = Bot(token=os.getenv("BOT_TOKEN"))

async def notify_admin_about_new_repair(data: dict):
    admin_ids = [a["tg_id"] for a in get_all_admins()]

    # Формирование текста заявки
    if data.get("is_short"):
        username = f"{data['username']}" if data.get("username") else "не указан"
        name = data.get("name", "арендатор Ibilsh")
        city = data.get("city", "-")
        phone = data.get("phone", "-")
        vin = data.get("vin") or "-"
        description = data.get("repair_description", "–")
    
        text = (
        f"🛠 <b>Новая заявка на ремонт от арендатора</b>\n\n"
        f"👤 <b>{name}</b> из {city}\n"
        f"📞 {phone} | {username}\n" 
        f"🔧 VIN: {vin}\n"
        f"📋 Проблема: {description}\n"
        f"🆔 <code>{data['tg_id']}</code>"
    )

    else:
        text = (
            f"🛠 <b>Новая заявка на ремонт</b>\n\n"
            f"👤 <b>{data['name']}</b> из {data['city']}\n"
            f"📞 {data['phone']} | {data.get('username', '-')}\n"
            f"🔧 VIN: {data.get('vin', '-')}\n"
            f"📋 Проблема: {data.get('problem', '-')}\n"
            f"🆔 <code>{data['tg_id']}</code>"
        )

    # Работа с фото (если есть)
    file_id = data.get("photo_file_id")
    if file_id:
        try:
            tg_file = await MAIN_BOT.get_file(file_id)
            file_url = tg_file.file_path

            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        os.makedirs("temp", exist_ok=True)
                        temp_path = os.path.join("temp", f"repair_photo_{data['tg_id']}.jpg")
                        async with aiofiles.open(temp_path, 'wb') as f:
                            await f.write(await response.read())

                        with open(temp_path, 'rb') as photo:
                             for admin_id in admin_ids:
                                await NOTIFIER_BOT.send_photo(
                                    chat_id=admin_id,
                                    photo=InputFile(photo),
                                    caption=text,
                                    parse_mode="HTML"
                            )
                        os.remove(temp_path)
                        return
        except TelegramError as e:
            print("❌ Ошибка при передаче фото:", e)

    # Без фото — просто текст
    for admin_id in admin_ids:
        await NOTIFIER_BOT.send_message(chat_id=admin_id, text=text, parse_mode="HTML")


#Заявка на вело
async def notify_admin_about_new_client(data: dict):
    admin_ids = [a["tg_id"] for a in get_all_admins()]

    text = (
        f"⚠️ <b>Внимание, поступила заявка на скутер</b>\n\n"
        f"👤 <b>{data['name']}</b>, {data['age']} лет\n"
        f"🏙️ Город: {data['city']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"📦 Тариф: {data.get('preferred_tariff', 'не указан')}\n"
        f"🔗 Username: {data['username']}\n"
        f"🆔 <code>{data['tg_id']}</code>\n\n"
        f"❗ После выдачи скутера не забудьте оформить данные нового пользователя в главном боте Ibilsh."
    )
    for admin_id in admin_ids:
        await NOTIFIER_BOT.send_message(
            chat_id=admin_id,
            text=text,
            parse_mode="HTML"
        )


# Отправка заявки на ремонт мастеру
async def send_repair_to_master(master_id: int, repair: dict):
    text = (
        f"🔧 <b>Новая заявка на ремонт</b>\n\n"
        f"👤 <b>{repair['name']}</b> из {repair['city']}\n"
        f"📞 {repair['phone']} | {repair['username'] or '—'}\n"
        f"🛵 VIN: {repair['vin'] or '—'}\n"
        f"📋 Проблема: {repair['problem']}\n"
        f"🆔 <code>{repair['tg_id']}</code>"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ремонт завершён", callback_data=f"done_repair:{repair['id']}")
    ]])

    file_id = repair.get("photo_file_id")
    if file_id:
        try:
            os.makedirs("temp", exist_ok=True)
            tg_file = await MAIN_BOT.get_file(file_id)
            file_url = tg_file.file_path
            temp_path = os.path.join("temp", f"repair_to_master_{repair['tg_id']}.jpg")

            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(temp_path, 'wb') as f:
                            await f.write(await response.read())

                        with open(temp_path, 'rb') as photo:
                            await NOTIFIER_BOT.send_photo(
                                chat_id=master_id,
                                photo=InputFile(photo),
                                caption=text,
                                parse_mode="HTML",
                                reply_markup=keyboard
                            )
                        os.remove(temp_path)
                        return
        except Exception as e:
            print("❌ Ошибка при отправке фото мастеру:", e)

    # если фото нет или ошибка — отправить только текст
    await NOTIFIER_BOT.send_message(
        chat_id=master_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def notify_admin_about_postpone(tg_id: int, full_name: str, original_date, scheduled_date, with_fine: bool, fine_amount: int, vin: str):
    
    admin_ids = [a["tg_id"] for a in get_all_admins()]
    user_info = get_user_info(tg_id)

    fine_text = f"⚠️ Со штрафом: +{fine_amount}₽" if with_fine else "✅ Без штрафа"

    text = (
        f"<b>📅 Запрос на перенос платежа</b>\n\n"
        f"👤 {full_name}\n"
        f"🆔 <code>{tg_id}</code>\n"
        f"🛴 VIN: <code>{vin}</code>\n"
        f"📅 {original_date.strftime('%d.%m.%Y')} → {scheduled_date.strftime('%d.%m.%Y')}\n"
        f"{fine_text}"
    )
    for admin_id in admin_ids:

        await NOTIFIER_BOT.send_message(admin_id, text, parse_mode="HTML")
