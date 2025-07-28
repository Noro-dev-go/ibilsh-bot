import uuid

import json

from yookassa import Configuration, Payment

import os

from dotenv import load_dotenv

# Конфигурация (пока тестовая)

load_dotenv()
Configuration.account_id = os.getenv("SHOP_ID")  # сюда вставишь свой shop_id
Configuration.secret_key = os.getenv("SECRET_KEY")  # сюда вставишь свой секретный API ключ

# Создание платежа
def create_payment(total_amount, return_url, payment_db_ids):
    """
    Создаёт платёж через ЮКассу.

    :param total_amount: Общая сумма платежа (в рублях)
    :param return_url: URL возврата после оплаты
    :param payment_db_ids: Список id платежей из твоей таблицы payments (которые будут оплачены)
    :return: (ссылка на оплату, внешний id платежа ЮКассы)
    """
    payment = Payment.create({
        "amount": {
            "value": f"{total_amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": return_url
        },
        "capture": True,
        "description": "Оплата аренды Ibilsh",
        "metadata": {
            "payment_db_ids": json.dumps(payment_db_ids)
        }
    }, uuid.uuid4())

    return payment.confirmation.confirmation_url, payment.id
