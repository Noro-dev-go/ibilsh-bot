from database.db import get_connection

from psycopg2.extras import DictCursor


ALLOWED_CLIENT_FIELDS = {
    "username", "full_name", "age", "city", "phone",
    "workplace", "client_photo_id", "passport_main_id", "passport_address_id"
}

# Добавление нового клиента
def add_client(telegram_id: int, username: str, full_name: str, age: int, city: str, phone: str, workplace: str, client_photo_id: str, passport_main_id: str, passport_address_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO clients (telegram_id, username, full_name, age, city, phone, workplace, client_photo_id, passport_main_id, passport_address_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (telegram_id, username, full_name, age, city, phone, workplace, client_photo_id, passport_main_id, passport_address_id))
            client_id = cur.fetchone()[0]
        conn.commit()
    return client_id

# Получить клиента по telegram_id
def get_client_by_tg_id(telegram_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, username, full_name, age, city, phone, workplace, client_photo_id, passport_main_id, passport_address_id
                FROM clients
                WHERE telegram_id = %s
            """, (telegram_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "username": row[1],
                "full_name": row[2],
                "age": row[3],
                "city": row[4],
                "phone": row[5],
                "workplace": row[6],
                "client_photo_id": row[7],
                "passport_main_id": row[8],
                "passport_address_id": row[9]
            }

# Получить всех клиентов
def get_all_clients():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, telegram_id, username, full_name, age, city, phone, workplace, client_photo_id, passport_main_id, passport_address_id
                FROM clients
                ORDER BY full_name ASC
            """)
            rows = cur.fetchall()

            clients = []
            for row in rows:
                clients.append({
                    "id": row[0],
                    "telegram_id": row[1],
                    "username": row[2],
                    "full_name": row[3],
                    "age": row[4],
                    "city": row[5],
                    "phone": row[6],
                    "workplace": row[7],
                    "client_photo_id": row[8],
                    "passport_main_id": row[9],
                    "passport_address_id": row[10]
                })
            return clients



def search_clients(query):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            sql = """
                SELECT * FROM clients
                WHERE
                    full_name ILIKE %s OR
                    city ILIKE %s OR
                    phone ILIKE %s OR
                    CAST(telegram_id AS TEXT) ILIKE %s OR
                    username ILIKE %s
            """
            param = f"%{query}%"
            cur.execute(sql, (param, param, param, param, param))
            return cur.fetchall()
        


def get_client_by_id(client_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, telegram_id, username, full_name, age, city, phone, workplace, client_photo_id, passport_main_id, passport_address_id
                FROM clients
                WHERE id = %s
            """, (client_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "telegram_id": row[1],
                "username": row[2],
                "full_name": row[3],
                "age": row[4],
                "city": row[5],
                "phone": row[6],
                "workplace": row[7],
                "client_photo_id": row[8],
                "passport_main_id": row[9],
                "passport_address_id": row[10]
            }
       
def update_client_field(client_id, field, value):
    if field not in ALLOWED_CLIENT_FIELDS:
        raise ValueError(f"Field '{field}' is not allowed to update.")
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = f"UPDATE clients SET {field} = %s WHERE id = %s"
            cur.execute(sql, (value, client_id))
            conn.commit()       



def get_custom_photos_by_client(client_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT file_id
                FROM client_photos
                WHERE client_id = %s
                ORDER BY uploaded_at
            """, (client_id,))
            return [row[0] for row in cur.fetchall()]            
        

def delete_client_full(client_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Получаем ID скутеров клиента
            cur.execute("SELECT id FROM scooters WHERE client_id = %s", (client_id,))
            scooter_ids = [row[0] for row in cur.fetchall()]

            # Удаление платежей
            if scooter_ids:
                cur.execute("DELETE FROM payments WHERE scooter_id = ANY(%s)", (scooter_ids,))
                cur.execute("DELETE FROM payment_postpones WHERE scooter_id = ANY(%s)", (scooter_ids,))

            # Удаление скутеров
            cur.execute("DELETE FROM scooters WHERE client_id = %s", (client_id,))

            # Удаление заметок
            cur.execute("DELETE FROM client_notes WHERE client_id = %s", (client_id,))

            # Удаление пользователей из users (по tg_id, надо получить)
            cur.execute("SELECT telegram_id FROM clients WHERE id = %s", (client_id,))
            result = cur.fetchone()
            if result:
                tg_id = result[0]
                cur.execute("DELETE FROM users WHERE tg_id = %s", (tg_id,))
                cur.execute("DELETE FROM pending_users WHERE tg_id = %s", (tg_id,))
                cur.execute("DELETE FROM pending_repairs WHERE tg_id = %s", (tg_id,))

            # Удаление самого клиента
            cur.execute("DELETE FROM clients WHERE id = %s", (client_id,))

        conn.commit()        