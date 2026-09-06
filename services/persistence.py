"""SQLite persistence for the audit log and review decisions (SPEC Section 5,
Section 6 "SQLite: audit_log + review_decisions", Phase 6).

Also stores a JSON snapshot of pipeline state per run so a run can be reloaded
(the plain-function-chain stand-in for a LangGraph checkpointer -- SPEC Section 0).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    event_id   TEXT PRIMARY KEY,
    run_id     TEXT NOT NULL,
    stage      TEXT NOT NULL,
    actor      TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    status     TEXT NOT NULL,
    notes      TEXT
);
CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    section_id  TEXT NOT NULL,
    reviewer    TEXT NOT NULL,
    decision    TEXT NOT NULL,
    comment     TEXT,
    timestamp   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_snapshots (
    run_id     TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_state (
    run_id     TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    blob       BLOB NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: Streamlit reruns the script on a pool of
        # ScriptRunner threads and reuses this process-global Store across them.
        # This prototype is single-user and Streamlit serialises script runs, so
        # sharing one connection is safe; a lock guards the few multi-statement
        # writes.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- audit log ------------------------------------------------------
    def log(self, run_id: str, stage: str, status: str, *, actor: str = "agent",
            notes: str | None = None) -> str:
        event_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?)",
                (event_id, run_id, stage, actor, _now(), status, notes),
            )
            self._conn.commit()
        return event_id

    def audit_trail(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT event_id, run_id, stage, actor, timestamp, status, notes "
            "FROM audit_log WHERE run_id=? ORDER BY timestamp, rowid",
            (run_id,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # -- review decisions --------------------------------------------
    def record_decision(self, run_id: str, section_id: str, reviewer: str,
                        decision: str, comment: str | None = None) -> str:
        decision_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO review_decisions VALUES (?,?,?,?,?,?,?)",
                (decision_id, run_id, section_id, reviewer, decision, comment, _now()),
            )
            self._conn.commit()
        return decision_id

    def decisions(self, run_id: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT decision_id, run_id, section_id, reviewer, decision, comment, timestamp "
            "FROM review_decisions WHERE run_id=? ORDER BY timestamp, rowid",
            (run_id,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # -- run snapshots (resumability) --------------------------------
    def save_snapshot(self, run_id: str, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO run_snapshots (run_id, updated_at, payload) VALUES (?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET updated_at=excluded.updated_at, "
                "payload=excluded.payload",
                (run_id, _now(), json.dumps(payload, default=str)),
            )
            self._conn.commit()

    def load_snapshot(self, run_id: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT payload FROM run_snapshots WHERE run_id=?", (run_id,)
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def list_runs(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT run_id, updated_at FROM run_snapshots ORDER BY updated_at DESC"
        )
        return [{"run_id": r[0], "updated_at": r[1]} for r in cur.fetchall()]

    # -- full-state blob (resumability) -----------------------------------
    def save_state_blob(self, run_id: str, blob: bytes) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO run_state (run_id, updated_at, blob) VALUES (?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET updated_at=excluded.updated_at, "
                "blob=excluded.blob",
                (run_id, _now(), sqlite3.Binary(blob)),
            )
            self._conn.commit()

    def load_state_blob(self, run_id: str) -> bytes | None:
        cur = self._conn.execute("SELECT blob FROM run_state WHERE run_id=?", (run_id,))
        row = cur.fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self._conn.close()


_default: Store | None = None


def get_store() -> Store:
    global _default
    if _default is None:
        _default = Store()
    return _default
