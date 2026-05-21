import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("SMARTBIN_DB_PATH", str(BASE_DIR / "smartbin.sqlite3")))
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _managed_connection():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _lock, _managed_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                level_oil REAL NOT NULL,
                level_solid REAL NOT NULL,
                ir_full INTEGER NOT NULL,
                raw_payload TEXT
            );

            CREATE TABLE IF NOT EXISTS discard_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                waste_type TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                raw_payload TEXT
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                compartment TEXT NOT NULL,
                level REAL NOT NULL,
                message TEXT NOT NULL
            );
            """
        )
        conn.commit()


def insert_telemetry(
    ts: str, level_oil: float, level_solid: float, ir_full: bool, payload: dict[str, Any]
) -> None:
    with _lock, _managed_connection() as conn:
        conn.execute(
            """
            INSERT INTO telemetry (ts, level_oil, level_solid, ir_full, raw_payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, level_oil, level_solid, int(ir_full), json.dumps(payload, ensure_ascii=True)),
        )
        conn.commit()


def insert_discard(ts: str, waste_type: str, quantity: int, payload: dict[str, Any]) -> None:
    with _lock, _managed_connection() as conn:
        conn.execute(
            """
            INSERT INTO discard_events (ts, waste_type, quantity, raw_payload)
            VALUES (?, ?, ?, ?)
            """,
            (ts, waste_type, quantity, json.dumps(payload, ensure_ascii=True)),
        )
        conn.commit()


def insert_alert(ts: str, compartment: str, level: float, message: str) -> None:
    with _lock, _managed_connection() as conn:
        conn.execute(
            """
            INSERT INTO alerts (ts, compartment, level, message)
            VALUES (?, ?, ?, ?)
            """,
            (ts, compartment, level, message),
        )
        conn.commit()


def get_latest_telemetry() -> dict[str, Any] | None:
    with _lock, _managed_connection() as conn:
        row = conn.execute(
            """
            SELECT ts, level_oil, level_solid, ir_full
            FROM telemetry
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return {
        "timestamp": row["ts"],
        "level_oil": float(row["level_oil"]),
        "level_solid": float(row["level_solid"]),
        "ir_full": bool(row["ir_full"]),
    }


def get_recent_alerts(limit: int = 20) -> list[dict[str, Any]]:
    with _lock, _managed_connection() as conn:
        rows = conn.execute(
            """
            SELECT ts, compartment, level, message
            FROM alerts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row["ts"],
            "compartment": row["compartment"],
            "level": float(row["level"]),
            "message": row["message"],
        }
        for row in rows
    ]


def get_stats(days: int = 7) -> dict[str, Any]:
    days = max(1, min(days, 90))
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).date()
    labels = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]

    with _lock, _managed_connection() as conn:
        rows = conn.execute(
            """
            SELECT date(ts) AS day, waste_type, SUM(quantity) AS total
            FROM discard_events
            WHERE date(ts) >= ?
            GROUP BY day, waste_type
            ORDER BY day ASC
            """,
            (start.isoformat(),),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT waste_type, SUM(quantity) AS total
            FROM discard_events
            GROUP BY waste_type
            """
        ).fetchall()

    oil_per_day = {day: 0 for day in labels}
    solid_per_day = {day: 0 for day in labels}
    for row in rows:
        day = row["day"]
        waste_type = (row["waste_type"] or "").strip().lower()
        if waste_type == "oleo" and day in oil_per_day:
            oil_per_day[day] = int(row["total"] or 0)
        elif waste_type == "solido" and day in solid_per_day:
            solid_per_day[day] = int(row["total"] or 0)

    total_oil = 0
    total_solid = 0
    for row in totals:
        waste_type = (row["waste_type"] or "").strip().lower()
        if waste_type == "oleo":
            total_oil = int(row["total"] or 0)
        elif waste_type == "solido":
            total_solid = int(row["total"] or 0)

    return {
        "labels": labels,
        "oil_daily": [oil_per_day[label] for label in labels],
        "solid_daily": [solid_per_day[label] for label in labels],
        "total_oil_discards": total_oil,
        "total_solid_discards": total_solid,
    }
