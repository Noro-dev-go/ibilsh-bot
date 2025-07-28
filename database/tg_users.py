import json
from datetime import datetime
from database.db import get_connection

def save_basic_user(tg_id: int, username: str | None):
    try:
        # === Сохраняем в базу данных ===
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tg_users (telegram_id, username)
            VALUES (%s, %s)
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username;
        """, (tg_id, username))
        conn.commit()
        cur.close()
        conn.close()

        print(f"[LOG] Сохранён пользователь: {tg_id}, {username}")

        # === Дополнительно сохраняем в logs.jsonl ===
        log_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tg_id": tg_id,
            "username": username
        }

        with open("logs.jsonl", "a", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False)
            f.write("\n")

    except Exception as e:
        print(f"[ERROR] Ошибка при сохранении tg_id: {e}")


def user_exists(tg_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tg_users WHERE telegram_id = %s", (tg_id,))
            return cur.fetchone() is not None        
