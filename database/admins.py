from database.db import get_connection

def is_admin(tg_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM admins WHERE tg_id = %s", (tg_id,))
            return cur.fetchone() is not None

def add_admin(tg_id: int, username: str = None, full_name: str = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO admins (tg_id, username, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (tg_id) DO NOTHING
            """, (tg_id, username, full_name))
        conn.commit()


def get_all_admins() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tg_id, username, full_name FROM admins")
            rows = cur.fetchall()

    return [
        {"tg_id": row[0], "username": row[1], "full_name": row[2]}
        for row in rows
    ]