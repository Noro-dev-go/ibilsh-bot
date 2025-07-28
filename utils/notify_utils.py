from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from database.db import get_connection
from database.clients import get_all_clients
from database.scooters import get_scooters_by_client
from database.payments import get_payments_by_scooter
from database.postpone import get_active_postpones, close_postpone
from utils.time_utils import get_today
import uuid




payment_confirm_registry = {}

# Основная функция уведомления по текущей дате
def format_payment_instruction_block(total_amount: int) -> str:
    return (
        f"\n💳 <b>Итого к оплате: {total_amount}₽</b>\n\n"
        f"📌 <b>ВАЖНО:</b>\n"
        f"1️⃣ Переведите сумму на номер <b>+79000000000</b>\n"
        f"2️⃣ Отправьте <b>скриншот перевода</b> в личные сообщения: <b>@ibilsh</b>\n"
        f"3️⃣ После этого <b>обязательно нажмите кнопку «✅ Я оплатил» ниже</b>\n\n"
        f"⚠️ Без выполнения всех трёх шагов платёж <b>не будет засчитан</b>."
    )

async def send_payment_notifications_with_button(bot: Bot, severity: str = "debug"):
    today = get_today()
    print(f"\n=== ▶️ ЗАПУСК УВЕДОМЛЕНИЙ ({severity.upper()}) | TODAY: {today} ===")

    clients = get_all_clients()
    print(f"👥 Найдено клиентов: {len(clients)}")

    for client in clients:
        tg_id = client['telegram_id']
        client_id = client['id']
        print(f"\n🔍 Клиент: {client['full_name']} (id={client_id})")

        scooters = get_scooters_by_client(client_id)
        print(f"🛵 Скутеров у клиента: {len(scooters)}")

        overdue = []
        postponed = []
        normal_payments = []

        # === Собираем платежи по каждому скутеру ===
        for scooter in scooters:
            scooter_id = scooter['id']
            payments = get_payments_by_scooter(scooter_id)
            postpones = get_active_postpones(scooter_id)

            skip_dates = {p[0] for p in postpones}        # original_date
            notify_dates = {p[1] for p in postpones}      # scheduled_date

            print(f"📜 Скутер {scooter['model']} → платежей: {len(payments)}, переносов: {len(postpones)}")

            for p in payments:
                pid, pay_date, amount, is_paid, _ = p
                print(f"   💵 Платёж {pid} | Дата: {pay_date} | Сумма: {amount} | Оплачен: {is_paid}")

                if is_paid:
                    continue

                # Просрочка
                if pay_date < today:
                    overdue.append((scooter, p))
                    print(f"     ⚠️ Помечен как ПРОСРОЧКА")

                # Сегодня (перенос или обычная оплата)
                elif pay_date == today:
                    postpone = next((post for post in postpones if post[1] == pay_date), None)
                    if postpone:
                        postponed.append((scooter, p, postpone))
                        print(f"     🔁 Помечен как ПЕРЕНОС")
                    else:
                        normal_payments.append((scooter, p))
                        print(f"     ✅ Помечен как ОБЫЧНАЯ ОПЛАТА")

        print(f"📊 Итог по клиенту → Просрочки: {len(overdue)}, Переносы: {len(postponed)}, Обычные платежи: {len(normal_payments)}")

        # === 1. Уведомления при ПРОСРОЧКЕ ===
        if severity == "overdue":
            print(f"📨 [OVERDUE] проверяем...")
            if not overdue:
                print(f"   ❌ Просрочек нет — уведомление не отправляем.")
                continue

    # ✅ Фильтруем платежи: убираем те, у которых есть перенос на scheduled_date
            filtered_overdue = []
            for scooter, row in overdue:
                scooter_id = scooter["id"]
                payment_date = row[1]  # дата платежа (original_date)
                active_postpones = get_active_postpones(scooter_id)

        # Если по этой дате есть перенос → не добавляем в список просрочек
                if any(p[0] == payment_date or p[1] == payment_date for p in active_postpones):
                    print(f"   ⏩ Пропущено: {scooter['model']} — перенос найден на {payment_date}")
                    continue

                filtered_overdue.append((scooter, row))

            if not filtered_overdue:
                print(f"   ❌ Все просрочки оказались с переносами → уведомления не шлём.")
                continue

            print(f"   ✅ Найдено {len(filtered_overdue)} просрочек (без переносов), отправляем уведомление…")

        # === отправка уведомления о просрочках ===
            total = len(filtered_overdue) * 1500 + sum(p[1][2] for p in filtered_overdue)
            text = "⚠️ <b>У вас есть просроченные платежи:</b>\n\n"
            payment_ids = [p[0] for _, p in filtered_overdue]

            for scooter, row in filtered_overdue:
                text += (
                f"🛵 <b>{scooter['model']}</b>\n"
                f"📅 Неделя: {row[1].strftime('%d.%m.%Y')}\n"
                f"💰 Тариф: {row[2]}₽ + Штраф: 1500₽ = <b>{row[2] + 1500}₽</b>\n\n"
            )

            text += format_payment_instruction_block(total)
            key = str(uuid.uuid4())[:8]
            payment_confirm_registry[key] = payment_ids
            cb_data = f"confirm_payment:{key}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Я оплатил", callback_data=cb_data)]
            ])

            try:
                await bot.send_message(chat_id=tg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
                print(f"✅ [OVERDUE] уведомление отправлено → {tg_id}")
            except Exception as e:
                print(f"[❌ overdue] {tg_id} → {e}")

            continue  # не даем дойти до стандартных уведомлений

        # === 2. Стандартные уведомления / переносы ===
        if severity == "standard":
            print(f"📨 [STANDARD] проверяем...")
            filtered_overdue = []
            for scooter, row in overdue:
                scooter_id = scooter["id"]
                payment_date = row[1]
                active_postpones = get_active_postpones(scooter_id)

                if any(p[0] == payment_date or p[1] == payment_date for p in active_postpones):
                    print(f"   ⏩ {scooter['model']} {payment_date} пропущен (перенос найден)")
                    continue

                filtered_overdue.append((scooter, row))

            if filtered_overdue:
                print(f"   ⚠️ У клиента есть ЧИСТЫЕ просрочки → стандартное уведомление не отправляем")
                continue

            # === Перенос — только по пятницам ===
            if postponed and today.weekday() == 4:
                print(f"   🔁 У клиента есть переносы → отправляем уведомление о переносах")

                # === отправка уведомления о переносах ===
                total = 0
                text = f"🔁 Обнаружены переносы по {len(postponed)} скутерам:\n\n"
                payment_ids = []

                for scooter, payment, postpone in postponed:
                    orig = postpone[0].strftime('%d.%m')
                    sched = postpone[1].strftime('%d.%m')
                    fine = postpone[3]
                    amount = scooter['weekly_price'] * 2 + fine
                    total += amount

                    payment_ids.append(payment[0])
                    sched_pid = next(
                        (p[0] for p in get_payments_by_scooter(scooter['id']) if p[1] == postpone[1]),
                        None
                    )
                    if sched_pid:
                        payment_ids.append(sched_pid)

                    text += (
                        f"🛵 <b>Модель: {scooter['model']}</b>\n"
                        f"📅 Перенос: с <b>{orig}</b> на <b>{sched}</b>\n"
                        f"💰 Сумма к оплате: <b>{amount}₽</b>\n"
                        f"{'⚠️ Со штрафом +' + str(fine) + '₽' if fine else '✅ Без штрафа'}\n\n"
                    )

                text += format_payment_instruction_block(total)
                key = str(uuid.uuid4())[:8]
                payment_confirm_registry[key] = payment_ids
                cb_data = f"confirm_payment:{key}"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Я оплатил", callback_data=cb_data)]
                ])

                try:
                    await bot.send_message(chat_id=tg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
                    print(f"✅ [POSTPONED] уведомление отправлено → {tg_id}")
                except Exception as e:
                    print(f"[❌ postpone] {tg_id} → {e}")

                continue

            # === 3. Обычные платежи (если нет просрочек и переносов) ===
            if normal_payments:
                print(f"   ✅ Найдено {len(normal_payments)} обычных платежей — отправляем уведомление")

                total = sum(p[2] for _, p in normal_payments)
                payment_ids = [p[0] for _, p in normal_payments]

                text = (
                    f"📅 Сегодня день оплаты аренды.\n"
                    f"💰 Сумма к оплате: <b>{total}₽</b>\n\n"
                    + format_payment_instruction_block(total)
                )

                key = str(uuid.uuid4())[:8]
                payment_confirm_registry[key] = payment_ids
                cb_data = f"confirm_payment:{key}"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Я оплатил", callback_data=cb_data)]
                ])

                try:
                    await bot.send_message(chat_id=tg_id, text=text, reply_markup=keyboard, parse_mode="HTML")
                    print(f"✅ [NORMAL] уведомление отправлено → {tg_id}")
                except Exception as e:
                    print(f"[❌ normal] {tg_id} → {e}")
            else:
                print(f"   ❌ Нет обычных платежей на сегодня")
