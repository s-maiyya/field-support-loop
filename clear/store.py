"""SQLite decision log (data/decisions.db - gitignored)."""
import sqlite3
from pathlib import Path

import pandas as pd

from .models import Alert, Decision

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "decisions.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    decided_at TEXT NOT NULL,
    seconds_to_decision REAL,
    hazard TEXT,
    location TEXT,
    action_id TEXT,
    trust_score INTEGER
)
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def save(decision: Decision, alert: Alert) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO decisions (alert_id, decision, reason, decided_at, seconds_to_decision, hazard, location, action_id, trust_score)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                decision.alert_id, decision.decision, decision.reason, decision.decided_at,
                decision.seconds_to_decision, alert.signal.hazard_type, alert.signal.location_name,
                alert.action.id if alert.action else None, alert.trust_score,
            ),
        )


def all_decisions() -> pd.DataFrame:
    with _conn() as c:
        return pd.read_sql_query(
            "SELECT decided_at, alert_id, location, hazard, action_id, trust_score, decision, reason, seconds_to_decision"
            " FROM decisions ORDER BY id DESC",
            c,
        )


def reject_counts() -> dict:
    """{hazard: number of rejections} - used by the Phase 6 feedback rule."""
    with _conn() as c:
        rows = c.execute("SELECT hazard, COUNT(*) FROM decisions WHERE decision='reject' GROUP BY hazard").fetchall()
    return {h: n for h, n in rows if h}
