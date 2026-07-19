"""
ARISE database helper.
- Memakai PostgreSQL jika tersedia.
- Kalau psycopg2 belum terpasang, DATABASE_URL belum benar, atau database mati,
  backend tetap bisa jalan dengan fallback in-memory di backend_api.py.
"""

import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # package belum terpasang
    psycopg2 = None
    RealDictCursor = None

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/arise_db",
)
USE_DB = os.getenv("ARISE_USE_DB", "1") != "0"


def is_db_enabled() -> bool:
    return USE_DB and psycopg2 is not None


@contextmanager
def get_conn():
    if not is_db_enabled():
        raise RuntimeError("Database disabled or psycopg2 is not installed")
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=3)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def database_status() -> Dict[str, Any]:
    if psycopg2 is None:
        return {"enabled": False, "connected": False, "reason": "psycopg2 belum terpasang"}
    if not USE_DB:
        return {"enabled": False, "connected": False, "reason": "ARISE_USE_DB=0"}
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"enabled": True, "connected": True, "reason": "ok"}
    except Exception as exc:
        return {"enabled": True, "connected": False, "reason": str(exc)}


def ensure_user(external_user_id: str) -> Optional[str]:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO users (external_user_id, full_name, role)
                    VALUES (%s, %s, 'siswa')
                    ON CONFLICT (external_user_id)
                    DO UPDATE SET external_user_id = EXCLUDED.external_user_id
                    RETURNING id;
                    """,
                    (external_user_id, f"Pengguna {external_user_id}"),
                )
                return str(cur.fetchone()["id"])
    except Exception as exc:
        print("[DB] ensure_user gagal:", exc)
        return None


def create_session_record(
    session_id: str,
    external_user_id: str,
    profile: str,
    avg_time: float,
    accuracy: float,
    variability: float,
    reduced_motion: bool,
    initial_level: int,
) -> bool:
    try:
        user_uuid = ensure_user(external_user_id)
        if not user_uuid:
            return False

        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO cognitive_profiles
                    (user_id, profile_category, avg_response_time, accuracy_rate, variability, reduced_motion)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (user_uuid, profile, avg_time, accuracy, variability, reduced_motion),
                )
                profile_id = cur.fetchone()["id"]

                cur.execute(
                    """
                    INSERT INTO sessions
                    (id, user_id, cognitive_profile_id, current_level, used_scenario_ids, current_scenario_id)
                    VALUES (%s, %s, %s, %s, %s, NULL)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    (session_id, user_uuid, profile_id, initial_level, []),
                )
        return True
    except Exception as exc:
        print("[DB] create_session_record gagal:", exc)
        return False


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        s.id,
                        u.external_user_id,
                        cp.profile_category,
                        s.current_level,
                        s.used_scenario_ids,
                        s.current_scenario_id
                    FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    LEFT JOIN cognitive_profiles cp ON cp.id = s.cognitive_profile_id
                    WHERE s.id = %s;
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                cur.execute(
                    """
                    SELECT
                        sr.round_number AS round,
                        sr.scenario_id,
                        sc.category,
                        sr.is_correct AS correct,
                        sr.level_before,
                        sr.level_after,
                        sr.response_time_seconds,
                        sr.ar_mode_shown AS ar_mode
                    FROM session_responses sr
                    JOIN scenarios sc ON sc.id = sr.scenario_id
                    WHERE sr.session_id = %s
                    ORDER BY sr.round_number;
                    """,
                    (session_id,),
                )
                history = [dict(r) for r in cur.fetchall()]

        return {
            "user_id": row["external_user_id"],
            "profile": row["profile_category"],
            "level": int(row["current_level"]),
            "used_scenario_ids": list(row["used_scenario_ids"] or []),
            "current_scenario_id": row["current_scenario_id"],
            "history": history,
        }
    except Exception as exc:
        print("[DB] load_session gagal:", exc)
        return None


def update_next_scenario(session_id: str, used_scenario_ids: List[int], current_scenario_id: int) -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sessions
                    SET used_scenario_ids = %s,
                        current_scenario_id = %s
                    WHERE id = %s;
                    """,
                    (used_scenario_ids, current_scenario_id, session_id),
                )
        return True
    except Exception as exc:
        print("[DB] update_next_scenario gagal:", exc)
        return False


def get_option_db_id(scenario_id: int, option_code: str) -> Optional[int]:
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id FROM scenario_options
                    WHERE scenario_id = %s AND option_code = %s;
                    """,
                    (scenario_id, option_code),
                )
                row = cur.fetchone()
                return int(row["id"]) if row else None
    except Exception as exc:
        print("[DB] get_option_db_id gagal:", exc)
        return None


def save_response_record(
    session_id: str,
    round_number: int,
    scenario_id: int,
    option_code: str,
    is_correct: bool,
    level_before: int,
    level_after: int,
    response_time_seconds: float,
    ar_mode: str,
    session_finished: bool,
) -> bool:
    try:
        option_db_id = get_option_db_id(scenario_id, option_code)
        if option_db_id is None:
            print("[DB] option_id tidak ditemukan di scenario_options")
            return False

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_responses
                    (session_id, round_number, scenario_id, option_id, is_correct,
                     level_before, level_after, response_time_seconds, ar_mode_shown)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id, round_number) DO NOTHING;
                    """,
                    (
                        session_id,
                        round_number,
                        scenario_id,
                        option_db_id,
                        is_correct,
                        level_before,
                        level_after,
                        response_time_seconds,
                        ar_mode,
                    ),
                )
                cur.execute(
                    """
                    UPDATE sessions
                    SET current_level = %s,
                        current_scenario_id = NULL,
                        ended_at = CASE WHEN %s THEN now() ELSE ended_at END
                    WHERE id = %s;
                    """,
                    (level_after, session_finished, session_id),
                )
        return True
    except Exception as exc:
        print("[DB] save_response_record gagal:", exc)
        return False
