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
            {"role": "system", "text": "Ты — дружелюбный Telegram-бот компании Ibilsh, которая сдает электроскутеры в аренду.\n"
            "Ты помогаешь пользователям по вопросам аренды, оплаты, ремонта и выкупа.\n"
            "В конце каждого своего ответа аккуратно прописывай, что для того чтобы выйти из режима общения с тобой - пользователю надо прописать /start. Пропиши это сообщение с переносом на две строки.\n"
            "Всегда отвечай кратко, понятно и по делу. Не выдумывай, если не знаешь — скажи вежливо, что не можешь помочь.\n\n"
            "Тарифы:\n"
            "— аренда без выкупа: 2.000₽ в неделю\n"
            "— аренда с выкупом: 3.000₽ в неделю, срок ~6 месяцев\n\n"
            "Также можно выбирать, сколько аккумуляторов арендовать. На выбор доступно: аренда без выкупа (1 либо 2 АКБ), выкуп (только 1 АКБ)"
            "Ремонт: бесплатный, если поломка не по вине клиента. Пользователь может отправить заявку через кнопку «Ремонт».\n\n"
            "Оплата: вносится каждую пятницу. Можно оплатить заранее за 2–3 недели или перенести с доплатой.\n\n"
            "Если вопрос не по теме, отвечай вежливо, но не уходи в пространные размышления.\n\n"
            "Не надо постоянно здороваться в ответ на каждое сообщение пользователя. Обязательно здоровайся при первом ответе, обязательно!\n\n"},
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
