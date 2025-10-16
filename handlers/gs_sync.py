from telegram import Update
from telegram.ext import CallbackQueryHandler, MessageHandler, ConversationHandler, filters, ContextTypes
from integrations.gsheets_fleet_matrix import upsert_by_column_index, find_column_by_transport_number

GS_WAIT_COL = 9201

async def gs_choice_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, client_id_str = q.data.split(":", 1)
    client_id = int(client_id_str)

    if context.user_data.get(f"gs_synced_{client_id}") is True:
        await q.edit_message_text("Выгрузка уже выполнена или пропущена.")
        return ConversationHandler.END

    if action == "gs_skip":
        context.user_data[f"gs_synced_{client_id}"] = True
        await q.edit_message_text("Ок, в Google Sheets не добавляем.")
        return ConversationHandler.END

    if action == "gs_add":
        context.user_data["gs_current_client"] = client_id
        await q.edit_message_text("Введи номер колонки в Google Sheets (например, 35).")
        return GS_WAIT_COL

async def gs_enter_col(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    client_id = context.user_data.get("gs_current_client")
    payload = context.user_data.get(f"gs_payload_{client_id}")

    if not (client_id and payload):
        await update.message.reply_text("Нет данных для выгрузки.")
        return ConversationHandler.END

    try:
        # 1) сначала — как 'Номер транс.' (35 / H35)
        col_index = find_column_by_transport_number(raw)
        if not col_index:
            # 2) не нашли по номеру — пробуем как прямой индекс
            col_index = int(raw)

        # Пишем строго в найденную колонку.
        # set_transport_number не задаём, чтобы не перетирать существующее значение.
        upsert_by_column_index(col_index, payload)

        context.user_data[f"gs_synced_{client_id}"] = True
        await update.message.reply_text(f"Готово. Клиент записан в колонку (индекс {col_index}).")
    except ValueError:
        await update.message.reply_text("Введи номер транспорта (напр., 35 или H35), либо индекс колонки числом.")
        return GS_WAIT_COL
    except Exception as e:
        await update.message.reply_text(f"Ошибка записи в Google Sheets: {e}")
    finally:
        context.user_data.pop("gs_current_client", None)

    return ConversationHandler.END

