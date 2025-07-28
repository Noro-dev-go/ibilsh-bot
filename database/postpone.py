from database.db import get_connection
from datetime import date, datetime
from typing import List, Optional, Tuple

from database.payments import update_payment_amount

from psycopg2.extras import RealDictCursor


def save_postpone_request(
    tg_id: int,
    scooter_id: int,
    original_date: date,
    scheduled_date: date,
    with_fine: bool,
    fine_amount: int
):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payment_postpones (
                    tg_id, scooter_id, original_date, scheduled_date, with_fine, fine_amount, is_closed, requested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, FALSE, NOW())
                ON CONFLICT (scooter_id, scheduled_date) DO UPDATE
                SET with_fine = EXCLUDED.with_fine,
                    fine_amount = EXCLUDED.fine_amount,
                    requested_at = CURRENT_TIMESTAMP,
                    original_date = EXCLUDED.original_date
            """, (tg_id, scooter_id, original_date, scheduled_date, with_fine, fine_amount))
        conn.commit()





def get_postpone_for_date(scooter_id: int, scheduled_date: date) -> Optional[dict]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT original_date, scheduled_date, with_fine, fine_amount, requested_at
                FROM payment_postpones
                WHERE scooter_id = %s AND scheduled_date = %s AND is_closed = FALSE
            """, (scooter_id, scheduled_date))
            return cur.fetchone()



def get_all_postpones() -> List[Tuple]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tg_id, scooter_id, original_date, scheduled_date, with_fine, fine_amount, is_closed, requested_at
                FROM payment_postpones
                ORDER BY tg_id ASC, scheduled_date ASC
            """)
            return cur.fetchall()



def get_active_postpones(scooter_id: int) -> List[Tuple]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT original_date, scheduled_date, with_fine, fine_amount, requested_at
                FROM payment_postpones
                WHERE scooter_id = %s AND is_closed = FALSE
            """, (scooter_id,))
            return cur.fetchall()



def close_postpone(scooter_id: int, date_to_close: date):
    if isinstance(date_to_close, str):
        try:
            date_to_close = datetime.strptime(date_to_close, "%Y-%m-%d").date()
        except ValueError:
            print(f"[ERROR] Неверный формат даты: {date_to_close}")
            return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE payment_postpones
                SET is_closed = TRUE
                WHERE scooter_id = %s AND (scheduled_date = %s OR original_date = %s) AND is_closed = FALSE
            """, (scooter_id, date_to_close, date_to_close))
        conn.commit()



def get_postpone_dates_by_tg_id(tg_id: int) -> Tuple[set, set]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT original_date, scheduled_date
                FROM payment_postpones
                WHERE tg_id = %s AND is_closed = FALSE
            """, (tg_id,))
            rows = cur.fetchall()
            original = set(row[0] for row in rows)
            scheduled = set(row[1] for row in rows)
            return original, scheduled



def close_postpone_if_paid(scooter_id: int, scheduled_date: date):
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Найдём перенос
            cur.execute("""
                SELECT original_date
                FROM payment_postpones
                WHERE scooter_id = %s AND scheduled_date = %s AND is_closed = FALSE
            """, (scooter_id, scheduled_date))
            result = cur.fetchone()
            if not result:
                return  # переноса нет или уже закрыт

            original_date = result[0]

            # Проверим оплату обеих дат
            cur.execute("""
                SELECT COUNT(*) 
                FROM payments 
                WHERE scooter_id = %s AND payment_date IN (%s, %s) AND is_paid = TRUE
            """, (scooter_id, original_date, scheduled_date))
            count = cur.fetchone()[0]

            if count == 2:
                # Обновим перенос
                cur.execute("""
                    UPDATE payment_postpones 
                    SET is_closed = TRUE 
                    WHERE scooter_id = %s AND scheduled_date = %s
                """, (scooter_id, scheduled_date))


def has_active_postpone(scooter_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM payment_postpones
        WHERE scooter_id = %s AND is_closed = FALSE
        LIMIT 1
    """, (scooter_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None                