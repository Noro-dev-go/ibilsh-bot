from database.db import get_connection

def save_pending_repair(data: dict):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pending_repairs (tg_id, username, name, city, phone, vin, problem, photo_file_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data["tg_id"],
                data["username"],
                data["name"],
                data["city"],
                data["phone"],
                data["vin"],
                data["problem"],
                data.get("photo_file_id")
            ))
            conn.commit()

def get_all_pending_repairs():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, tg_id, username, name, city, phone, vin, problem, photo_file_id, submitted_at
                FROM pending_repairs
                WHERE is_processed = FALSE
                ORDER BY submitted_at ASC
            """)
            return cur.fetchall()
        print(f"[DEBUG] Pending repairs: {rows}")  # 👈 добавь это
        return rows



def get_repair_by_id(repair_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, tg_id, username, name, city, phone, vin, problem, photo_file_id
                FROM pending_repairs WHERE id = %s
            """, (repair_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "tg_id": row[1],
                "username": row[2],
                "name": row[3],
                "city": row[4],
                "phone": row[5],
                "vin": row[6],
                "problem": row[7],
                "photo_file_id": row[8]
            }




def mark_repair_as_processed(repair_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pending_repairs SET is_processed = TRUE WHERE id = %s
            """, (repair_id,))
            conn.commit()



def add_done_repair(repair: dict):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
    INSERT INTO repairs_done (
        id, tg_id, username, name, city, phone, vin, problem, photo_file_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (
    repair["id"],
    repair["tg_id"],
    repair["username"],
    repair["name"],
    repair["city"],
    repair["phone"],
    repair["vin"],
    repair["problem"],
    repair.get("photo_file_id")
))
    conn.commit()
    conn.close()



def get_all_done_repairs(tg_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT completed_at, problem, photo_file_id
                FROM repairs_done
                WHERE tg_id = %s
                ORDER BY completed_at DESC
            """, (tg_id,))
            return cur.fetchall()
        

def get_all_done_repairs_admin():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, tg_id, username, name, city, phone, vin, problem, photo_file_id, completed_at
                FROM repairs_done
                ORDER BY completed_at DESC
            """)
            return cur.fetchall()