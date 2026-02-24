import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

DB_PATH = Path(__file__).with_name("symptoms.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
ADDITIONAL_COLUMNS = {
    "time_of_day": "TEXT",
    "pain": "INTEGER",
    "global_health": "INTEGER",
    "top_culprit": "TEXT",
    "analysis_json": "TEXT",
    "entry_json": "TEXT",
}

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_additional_columns(conn: sqlite3.Connection) -> None:
    existing_cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(entries)").fetchall()
    }
    for col_name, col_type in ADDITIONAL_COLUMNS.items():
        if col_name not in existing_cols:
            conn.execute(f"ALTER TABLE entries ADD COLUMN {col_name} {col_type}")

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_additional_columns(conn)

def _top_culprit_from_analysis(analysis: Dict[str, Any]) -> str:
    probs = analysis.get("culprit_probabilities_percent", {}) if analysis else {}
    if not probs:
        return "General"
    return max(probs.items(), key=lambda item: item[1])[0]

def add_entry(entry: Dict[str, Any]) -> None:
    analysis = entry.get("analysis", {}) or {}
    symptoms = entry.get("symptoms", {}) or {}
    context = entry.get("context", {}) or {}
    meds = entry.get("meds", {}) or {}

    top_culprit = _top_culprit_from_analysis(analysis)
    meds_summary = ", ".join(
        f"{k}={'yes' if bool(v) else 'no'}" for k, v in meds.items()
    )

    with get_conn() as conn:
        _ensure_additional_columns(conn)
        conn.execute(
            """
            INSERT INTO entries (
                ts, symptom, severity, notes, triggers, meds, sleep_hours, stress,
                time_of_day, pain, global_health, top_culprit, analysis_json, entry_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.get("timestamp"),
                top_culprit,
                int(symptoms.get("pain_0_10", 0) or 0),
                entry.get("notes") or "",
                "",
                meds_summary,
                None,
                int(context.get("stress_0_3", 0) or 0),
                entry.get("time_of_day"),
                int(symptoms.get("pain_0_10", 0) or 0),
                int(symptoms.get("global_health_0_10", 0) or 0),
                top_culprit,
                json.dumps(analysis, ensure_ascii=False),
                json.dumps(entry, ensure_ascii=False),
            ),
        )

def list_entries(limit=200):
    with get_conn() as conn:
        _ensure_additional_columns(conn)
        rows = conn.execute(
            """
            SELECT
                id, ts, symptom, severity, notes, triggers, meds, sleep_hours, stress,
                time_of_day, pain, global_health, top_culprit, analysis_json, entry_json
            FROM entries
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    parsed_rows: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["analysis"] = json.loads(item.get("analysis_json") or "{}")
        except json.JSONDecodeError:
            item["analysis"] = {}
        try:
            item["entry"] = json.loads(item.get("entry_json") or "{}")
        except json.JSONDecodeError:
            item["entry"] = {}
        parsed_rows.append(item)

    return parsed_rows
