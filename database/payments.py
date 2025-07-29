from database.db import get_connection
from psycopg2.extras import execute_values
from utils.schedule_utils import get_next_fridays
from utils.time_utils import get_today
from datetime import date, timedelta

# Создать график платежей по скутеру (массовая вставка новых платежей)
def create_payment_schedule(scooter_id: int, payment_dates: list, weekly_price: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            values = [(scooter_id, d, weekly_price, False, None, None) for d in payment_dates]
            execute_values(
                cur,
                """
                INSERT INTO payments (scooter_id, payment_date, amount, is_paid, paid_at, proof_path)
                VALUES %s
                ON CONFLICT (scooter_id, payment_date) DO NOTHING
                """,
                values
            )
        conn.commit()


# Получить все платежи по скутеру
def get_payments_by_scooter(scooter_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, payment_date, amount, is_paid, paid_at
        FROM payments
        WHERE scooter_id = %s
        ORDER BY payment_date ASC
    """, (scooter_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows



# Получить все неоплаченные платежи по клиенту на конкретную дату (для подсчёта сумм)
def get_payments_for_date_by_client(client_id: int, target_date):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.amount
                FROM payments p
                JOIN scooters s ON p.scooter_id = s.id
                WHERE s.client_id = %s AND p.payment_date = %s AND p.is_paid = FALSE
            """, (client_id, target_date))
            return cur.fetchall()


# Отметить платежи как оплаченные (по списку ID платежей)
def mark_payments_as_paid(payment_ids: list, proof_path: str = None):
    if not payment_ids:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            if proof_path:
                cur.execute("""
                    UPDATE payments
                    SET is_paid = TRUE, paid_at = NOW(), proof_path = %s
                    WHERE id = ANY(%s)
                """, (proof_path, payment_ids))
            else:
                cur.execute("""
                    UPDATE payments
                    SET is_paid = TRUE, paid_at = NOW()
                    WHERE id = ANY(%s)
                """, (payment_ids,))
        conn.commit()


# Продление аренды (новая функция для продления)
def save_payment_schedule_by_scooter(scooter_id: int, dates: list, weekly_price: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            values = [(scooter_id, d, weekly_price, False, None, None) for d in dates]
            execute_values(
                cur,
                """
                INSERT INTO payments (scooter_id, payment_date, amount, is_paid, paid_at, proof_path)
                VALUES %s
                ON CONFLICT (scooter_id, payment_date) DO NOTHING
                """,
                values
            )
        conn.commit()



def refresh_payment_schedule_by_scooter(scooter_id: int, start_date, weeks: int, weekly_price: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            # ❗ Удаляем только неоплаченные платежи
            cur.execute("""
                DELETE FROM payments
                WHERE scooter_id = %s AND is_paid = FALSE
            """, (scooter_id,))

            # ✅ Генерируем даты без повторного сдвига
            new_dates = [start_date + timedelta(weeks=i) for i in range(weeks)]

            values = [
                (scooter_id, d, weekly_price, False, None, None)
                for d in new_dates
            ]

            execute_values(
                cur,
                """
                INSERT INTO payments (scooter_id, payment_date, amount, is_paid, paid_at, proof_path)
                VALUES %s
                """,
                values
            )

        conn.commit()


def get_unpaid_payments_by_scooter(scooter_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, payment_date, amount, fine, scooter_id
                FROM payments
                WHERE scooter_id = %s AND is_paid = FALSE
                ORDER BY payment_date ASC
            """, (scooter_id,))
            return cur.fetchall()        
        



def update_payment_amount(scooter_id: int, payment_date: date, new_amount: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE payments
                SET amount = %s
                WHERE scooter_id = %s AND payment_date = %s
            """, (new_amount, scooter_id, payment_date))
        conn.commit()



def get_last_and_next_friday(reference: date = date.today()):
    weekday = reference.weekday()
    last_friday = reference - timedelta(days=(weekday - 4) % 7 or 7)
    next_friday = reference + timedelta(days=(4 - weekday) % 7)
    return last_friday, next_friday





def get_all_unpaid_clients_by_dates(dates: list):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.full_name, c.phone, c.username, p.payment_date, p.amount
                FROM payments p
                JOIN scooters s ON p.scooter_id = s.id
                JOIN clients c ON s.client_id = c.id
                WHERE p.payment_date = ANY(%s) AND p.is_paid = FALSE
                ORDER BY p.payment_date, c.full_name
            """, (dates,))
            return cur.fetchall()