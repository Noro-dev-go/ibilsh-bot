from datetime import date
from typing import List

from database.db import get_connection
from typing import Optional
from psycopg2.extras import RealDictCursor

def format_payment_schedule(tg_id: int, rows: List[tuple], postpones: List[dict]) -> str:
    if not rows:
        return "❗️График платежей не найден."

    lines = ["\n📅<b>График платежей:\n</b>"]

    # Словари для логики переноса
    original_dates = {p["original_date"] for p in postpones}
    schedule_to_original = {p["scheduled_date"]: p["original_date"] for p in postpones}

    paid_double_marker = set()

    for payment_id, date, amount, is_paid, paid_at in rows:
        paid_date = paid_at.strftime('%d.%m.%Y') if paid_at else "-"
        line = ""

        # Сначала проверяем даты переноса (старые даты)
        if date in original_dates:
            status = "⬇️"
            line = f"{status} {date.strftime('%d.%m')} 0Р (Оплачено: {paid_date})"
            lines.append(line)

            # Добавляем маркер для двойной оплаты
            for sched, orig in schedule_to_original.items():
                if orig == date:
                    paid_double_marker.add(sched)

        # . Обычные даты
        elif is_paid:
            status = "✅"
            line = f"{status} {date.strftime('%d.%m')} {amount}Р (Оплачено: {paid_date})"
            lines.append(line)

        #  Неоплаченные недели
        else:
            status = "⬜"
            line = f"{status} {date.strftime('%d.%m')} {amount}Р (Оплачено: -)"
            lines.append(line)

    return "\n".join(lines)



def get_payment_id_by_date(scooter_id: int, payment_date: date) -> Optional[int]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id FROM payments
                WHERE scooter_id = %s AND payment_date = %s
                LIMIT 1
            """, (scooter_id, payment_date))
            result = cur.fetchone()
            return result["id"] if result else None
