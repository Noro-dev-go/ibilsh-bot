# database/admin_security.py
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from database.db import get_connection

UTC = timezone.utc

def _row_to_tuple(row) -> Tuple[int, Optional[datetime], Optional[datetime]]:
    # attempts, locked_until, last_attempt_at
    return (row[0], row[1], row[2])

def get_security_state(tg_id: int) -> Tuple[int, Optional[datetime], Optional[datetime]]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT attempts, locked_until, last_attempt_at
            FROM admin_locks WHERE tg_id = %s
        """, (tg_id,))
        row = cur.fetchone()
        if not row:
            return (0, None, None)
        return _row_to_tuple(row)

def set_lock(tg_id: int, minutes: int, reset_attempts: bool = True) -> datetime:
    lock_until = datetime.now(UTC) + timedelta(minutes=minutes)
    with get_connection() as conn, conn.cursor() as cur:
        if reset_attempts:
            cur.execute("""
                INSERT INTO admin_locks (tg_id, attempts, locked_until, last_attempt_at)
                VALUES (%s, 0, %s, NOW())
                ON CONFLICT (tg_id) DO UPDATE
                SET attempts = 0, locked_until = EXCLUDED.locked_until, last_attempt_at = NOW()
            """, (tg_id, lock_until))
        else:
            cur.execute("""
                INSERT INTO admin_locks (tg_id, attempts, locked_until, last_attempt_at)
                VALUES (%s, 0, %s, NOW())
                ON CONFLICT (tg_id) DO UPDATE
                SET locked_until = EXCLUDED.locked_until, last_attempt_at = NOW()
            """, (tg_id, lock_until))
        conn.commit()
    return lock_until

def clear_lock_and_attempts(tg_id: int):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE admin_locks
            SET attempts = 0, locked_until = NULL, last_attempt_at = NOW()
            WHERE tg_id = %s
        """, (tg_id,))
        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO admin_locks (tg_id, attempts, locked_until, last_attempt_at)
                VALUES (%s, 0, NULL, NOW())
            """, (tg_id,))
        conn.commit()

def increment_attempt(tg_id: int) -> int:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO admin_locks (tg_id, attempts, last_attempt_at)
            VALUES (%s, 1, NOW())
            ON CONFLICT (tg_id) DO UPDATE
            SET attempts = admin_locks.attempts + 1,
                last_attempt_at = NOW()
            RETURNING attempts
        """, (tg_id,))
        attempts = cur.fetchone()[0]
        conn.commit()
    return attempts

def is_locked(tg_id: int) -> Optional[datetime]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT locked_until FROM admin_locks WHERE tg_id = %s", (tg_id,))
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return row[0]

def get_last_attempt_at(tg_id: int) -> Optional[datetime]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT last_attempt_at FROM admin_locks WHERE tg_id = %s", (tg_id,))
        row = cur.fetchone()
        return row[0] if row else None

