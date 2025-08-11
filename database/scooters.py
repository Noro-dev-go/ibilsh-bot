from database.db import get_connection

ALLOWED_FIELDS = {
    "model", "vin", "motor_vin", "issue_date",
    "tariff_type", "weekly_price", "buyout_weeks",
    "has_contract", "has_second_keys", "has_tracker",
    "has_limiter", "has_pedals", "has_sim"
}

def add_scooter(client_id: int, data: dict):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scooters (
                    client_id, model, vin, motor_vin, issue_date, 
                    tariff_type, weekly_price, buyout_weeks,
                    has_contract, has_second_keys, has_tracker, has_limiter, has_pedals, has_sim
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                client_id,
                data["model"],
                data["vin"],
                data["motor_vin"],
                data["issue_date"],
                data["tariff_type"],
                data["weekly_price"],
                data.get("buyout_weeks"),
                data.get("has_contract", False),
                data.get("has_second_keys", False),
                data.get("has_tracker", False),
                data.get("has_limiter", False),
                data.get("has_pedals", False),
                data.get("has_sim", False),
            ))
            scooter_id = cur.fetchone()[0]
        conn.commit()
    return scooter_id



def get_scooters_by_client(client_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, model, vin, motor_vin, issue_date, tariff_type, weekly_price, buyout_weeks,
                       has_contract, has_second_keys, has_tracker, has_limiter, has_pedals, has_sim
                FROM scooters
                WHERE client_id = %s
                ORDER BY id
            """, (client_id,))
            rows = cur.fetchall()

            scooters = []
            for row in rows:
                scooters.append({
                    "id": row[0],
                    "model": row[1],
                    "vin": row[2],
                    "motor_vin": row[3],
                    "issue_date": row[4],
                    "tariff_type": row[5],
                    "weekly_price": row[6],
                    "buyout_weeks": row[7],
                    "has_contract": row[8],
                    "has_second_keys": row[9],
                    "has_tracker": row[10],
                    "has_limiter": row[11],
                    "has_pedals": row[12],
                    "has_sim": row[13],
                })
            return scooters


def get_scooter_by_id(scooter_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, client_id, model, vin, motor_vin, issue_date, tariff_type, weekly_price, buyout_weeks,
                       has_contract, has_second_keys, has_tracker, has_limiter, has_pedals, has_sim
                FROM scooters
                WHERE id = %s
            """, (scooter_id,))
            row = cur.fetchone()

            if row:
                return {
                    "id": row[0],
                    "client_id": row[1],
                    "model": row[2],
                    "vin": row[3],
                    "motor_vin": row[4],
                    "issue_date": row[5],
                    "tariff_type": row[6],
                    "weekly_price": row[7],
                    "buyout_weeks": row[8],
                    "has_contract": row[9],
                    "has_second_keys": row[10],
                    "has_tracker": row[11],
                    "has_limiter": row[12],
                    "has_pedals": row[13],
                    "has_sim": row[14],
                }
            else:
                return None
            


def update_scooter_field(scooter_id, field, value):
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Field '{field}' is not allowed to update.")
    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = f"UPDATE scooters SET {field} = %s WHERE id = %s"
            cur.execute(sql, (value, scooter_id))
            conn.commit()
