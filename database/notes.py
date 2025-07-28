from database.db import get_connection

# Добавить заметку
def add_note(client_id: int, note: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO client_notes (client_id, note)
                VALUES (%s, %s)
            """, (client_id, note))
        conn.commit()

# Получить последние N заметок по клиенту
def get_notes(client_id: int, limit: int = 5):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT note, created_at
                FROM client_notes
                WHERE client_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (client_id, limit))
            return cur.fetchall()