from database.db import get_connection

def check_user(tg_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE tg_id = %s", (tg_id,))
            return cur.fetchone() is not None

def get_user_info(tg_id: int) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT username, full_name, phone, has_scooter 
                FROM users 
                WHERE tg_id = %s
            """, (tg_id,))
            row = cur.fetchone()
            if not row:
                return {}

            return {
                "username": row[0],
                "full_name": row[1],
                "phone": row[2],
                "has_scooter": row[3]
            }


def add_user(tg_id: int, username: str, full_name: str, phone: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (tg_id, username, full_name, phone)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (tg_id) DO NOTHING
            """, (tg_id, username, full_name, phone))
            conn.commit()


def set_user_has_scooter(tg_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users
                SET has_scooter = TRUE
                WHERE tg_id = %s
            """, (tg_id,))
        conn.commit()


def get_renters_tg_ids() -> list[int]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tg_id FROM users WHERE has_scooter = TRUE")
            return [row[0] for row in cur.fetchall()]