"""SQLite buyer profile and query history memory (Section 3, 7, & 11)."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "buyer_memory.sqlite"


class BuyerMemory:
    """Local SQLite store for buyer budget, persona, preferred sets/conditions, and past queries."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS buyer_profiles (
                    session_id TEXT PRIMARY KEY,
                    budget REAL,
                    persona TEXT,
                    preferred_sets TEXT,
                    preferred_condition TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    raw_query TEXT NOT NULL,
                    parsed_json TEXT,
                    top_pick_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def get_profile(self, session_id: str) -> dict[str, Any]:
        """Load saved buyer defaults for a session."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM buyer_profiles WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return {}
        return {
            "session_id": row["session_id"],
            "budget": row["budget"],
            "persona": row["persona"],
            "preferred_sets": json.loads(row["preferred_sets"] or "[]"),
            "preferred_condition": row["preferred_condition"],
            "updated_at": row["updated_at"],
        }

    def save_profile(
        self,
        session_id: str,
        budget: Optional[float] = None,
        persona: Optional[str] = None,
        preferred_set: Optional[str] = None,
        preferred_condition: Optional[str] = None,
    ) -> dict[str, Any]:
        """Upsert buyer preferences, preserving previously saved values when new ones are None."""
        existing = self.get_profile(session_id)
        merged_budget = budget if budget is not None else existing.get("budget")
        merged_persona = persona if persona is not None else existing.get("persona")
        merged_condition = (
            preferred_condition
            if preferred_condition is not None
            else existing.get("preferred_condition")
        )
        sets: list[str] = list(existing.get("preferred_sets", []))
        if preferred_set and preferred_set not in sets:
            sets.append(preferred_set)

        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO buyer_profiles (
                    session_id, budget, persona, preferred_sets, preferred_condition, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    budget = excluded.budget,
                    persona = excluded.persona,
                    preferred_sets = excluded.preferred_sets,
                    preferred_condition = excluded.preferred_condition,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    merged_budget,
                    merged_persona,
                    json.dumps(sets),
                    merged_condition,
                    now,
                ),
            )
        return self.get_profile(session_id)

    def log_query(
        self,
        session_id: str,
        raw_query: str,
        parsed_dict: Optional[dict[str, Any]] = None,
        top_pick_id: Optional[str] = None,
    ) -> None:
        """Append a completed query to history."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO query_history (session_id, raw_query, parsed_json, top_pick_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    raw_query,
                    json.dumps(parsed_dict) if parsed_dict is not None else None,
                    top_pick_id,
                    now,
                ),
            )

    def get_history(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return most recent queries for a session."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT raw_query, parsed_json, top_pick_id, created_at
                FROM query_history
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            {
                "raw_query": r["raw_query"],
                "parsed": json.loads(r["parsed_json"]) if r["parsed_json"] else None,
                "top_pick_id": r["top_pick_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
