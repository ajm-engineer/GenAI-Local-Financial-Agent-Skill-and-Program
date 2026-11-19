from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "digest_history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT NOT NULL,
    digest_text     TEXT,
    fact_block      TEXT,
    guardrail_hits  TEXT,
    data_errors     TEXT,
    delivered       INTEGER NOT NULL DEFAULT 0,
    generated       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_runs_run_at ON runs(run_at);
"""


def init() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def record(
    digest: dict,
    errors: list[str],
    delivered: bool,
) -> int:
    conn = init()
    try:
        cur = conn.execute(
            """
            INSERT INTO runs
                (run_at, digest_text, fact_block, guardrail_hits,
                 data_errors, delivered, generated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dt.datetime.now().isoformat(timespec="seconds"),
                digest.get("text", ""),
                digest.get("fact_block", ""),
                json.dumps(digest.get("guardrail_hits", [])),
                json.dumps(errors),
                int(delivered),
                int(digest.get("generated", False)),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def recent(limit: int = 10) -> list[dict]:
    conn = init()
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY run_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def summary() -> None:
    runs = recent(30)
    if not runs:
        print("No runs recorded yet.")
        return

    delivered = sum(r["delivered"] for r in runs)
    flagged = sum(1 for r in runs if json.loads(r["guardrail_hits"]))
    degraded = sum(1 for r in runs if not r["generated"])

    print(f"Last {len(runs)} runs:")
    print(f"  delivered:        {delivered}")
    print(f"  guardrail hits:   {flagged}")
    print(f"  degraded (no API):{degraded}")
    print(f"  most recent:      {runs[0]['run_at']}")

    if flagged:
        print("\nRuns with guardrail hits are worth reading. The system was")
        print("told not to produce opinion and did anyway.")
