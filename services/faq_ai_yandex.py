import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

def ask_yandex_gpt(question: str) -> str:
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
    "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
    "completionOptions": {
        "stream": False,
        "temperature": 0.4,
        "maxTokens": 200
    },
    "messages": [
        {
            "role": "system",
            "text": (
                "Ты — дружелюбный Telegram-бот компании Ibilsh, которая сдает электроскутеры в аренду. "
                "Ты помогаешь пользователям по вопросам аренды, оплаты, ремонта и выкупа электроскутеров. "
                "В конце каждого своего ответа аккуратно прописывай, что для того чтобы выйти из режима общения с тобой — пользователю надо прописать /start. "
                "Пропиши это сообщение с переносом на две строки. "
                "Всегда отвечай кратко, понятно и по делу. Если не знаешь ответа — вежливо скажи, что не можешь помочь. "
                "Обязательно поздоровайся при первом ответе пользователю, но не повторяй приветствие в каждом сообщении. "
                "\n\nТарифы:\n— аренда без выкупа: 2.000₽ в неделю\n— аренда с выкупом: 3.000₽ в неделю, срок ~12 месяцев\n"
                "— при оформлении можно выбрать 1 или 2 аккумулятора (при выкупе — только 1 АКБ). "
                "\n\nРемонт:\n— если человек арендует электровелосипед Ibilsh, ремонт бесплатный, если поломка не по вине клиента. Обязательно укажи то, что ремонт бесплатный если человек арендует электровелосипед у Ibilsh! "
                "— если поломка спорная или не связана с арендой, дружелюбно объясни, что каждый случай рассматривается индивидуально. "
                "— напомни, что заявку на ремонт можно оставить через кнопку «Необходим ремонт» в главном меню бота. "
                "\n\nОплата:\n— вносится каждую пятницу. Можно оплатить сразу за 2–3 недели вперёд или перенести платеж с доплатой. "
                "\n\nЕсли вопрос не по теме — ответь вежливо и дай понять, что бот предназначен только для помощи по аренде, оплате, ремонту и выкупу."
            )
        },
        {"role": "user", "text": question}
    ]
}
    try:
        print("📤 Отправляем в YandexGPT:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        response = requests.post(url, headers=headers, json=payload)

        if not response.ok:
            print(f"🔴 Ответ от Yandex: {response.status_code} — {response.text}")
            return "Не удалось получить ответ от YandexGPT. Попробуйте позже."

        data = response.json()

        if (
            "result" in data and
            "alternatives" in data["result"] and
            len(data["result"]["alternatives"]) > 0 and
            "message" in data["result"]["alternatives"][0] and
            "text" in data["result"]["alternatives"][0]["message"]
        ):
            return data["result"]["alternatives"][0]["message"]["text"]
        else:
            print("⚠️ Ответ не содержит ожидаемых полей:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return "Ответ от YandexGPT был получен, но в неожиданном формате."

    except Exception as e:
        print("YandexGPT error:", e)
        return "Ошибка при запросе к YandexGPT. Попробуйте позже."
