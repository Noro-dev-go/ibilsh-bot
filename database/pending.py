import psycopg2
import os
from dotenv import load_dotenv
from database.db import get_connection

load_dotenv()

def save_pending_user(data: dict):
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO pending_users (tg_id, username, name, age, city, phone, preferred_tariff)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (tg_id) DO NOTHING
""", (
    data["tg_id"],
    data.get("username"),
    data["name"],
    data["age"],
    data["city"],
    data["phone"],
    data.get("preferred_tariff"),
    
))

    conn.commit()
    cur.close()
    conn.close()


def get_all_pending_users():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT tg_id, username, name, age, city, phone, preferred_tariff, submitted_at
                FROM pending_users
                WHERE is_processed = FALSE
                ORDER BY submitted_at ASC
            """)
            return cur.fetchall()
        

def delete_pending_user(tg_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM pending_users
                WHERE tg_id = %s
            """, (tg_id,))
        conn.commit()        