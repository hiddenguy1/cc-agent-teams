"""SQLite storage layer for Agent Team coordination."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


def _team_db_path(team_name: str) -> Path:
    d = Path.home() / ".agent-team" / "teams" / team_name
    d.mkdir(parents=True, exist_ok=True)
    return d / "team.db"


class TeamDB:
    """SQLite-backed storage for messages, locks, and tasks."""

    def __init__(self, team_name: str):
        self.team_name = team_name
        self._db_path = _team_db_path(team_name)
        self._conn = sqlite3.connect(str(self._db_path), timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                timestamp REAL NOT NULL,
                from_agent TEXT NOT NULL,
                "to" TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'message',
                content TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                read_by_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_messages_to ON messages("to");
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);

            CREATE TABLE IF NOT EXISTS locks (
                file_path TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                acquired_at REAL NOT NULL,
                task_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                subject TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                owner TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL,
                completed_at REAL,
                blocked_by_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── Messages ──────────────────────────────────────────────────

    def send_message(
        self, from_agent: str, to: str, content: str,
        msg_type: str = "message", metadata: dict | None = None,
    ) -> str:
        msg_id = f"msg-{uuid.uuid4().hex[:12]}"
        self._conn.execute(
            'INSERT INTO messages (id, timestamp, from_agent, "to", type, content, metadata_json) '
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, time.time(), from_agent, to, msg_type, content, json.dumps(metadata or {})),
        )
        self._conn.commit()
        return msg_id

    def get_messages(self, agent_name: str, limit: int = 50, unread_only: bool = False) -> list[dict]:
        if unread_only:
            rows = self._conn.execute(
                'SELECT * FROM messages WHERE ("to"=? OR "to"=\'all\') '
                "AND from_agent != ? AND read_by_json NOT LIKE ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (agent_name, agent_name, f'%"{agent_name}"%', limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                'SELECT * FROM messages WHERE ("to"=? OR "to"=\'all\') '
                "AND from_agent != ? ORDER BY timestamp DESC LIMIT ?",
                (agent_name, agent_name, limit),
            ).fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    def get_unread_count(self, agent_name: str) -> int:
        row = self._conn.execute(
            'SELECT COUNT(*) FROM messages WHERE ("to"=? OR "to"=\'all\') '
            "AND from_agent != ? AND read_by_json NOT LIKE ?",
            (agent_name, agent_name, f'%"{agent_name}"%'),
        ).fetchone()
        return row[0] if row else 0

    def mark_read(self, agent_name: str, msg_ids: list[str]) -> None:
        for msg_id in msg_ids:
            row = self._conn.execute(
                "SELECT read_by_json FROM messages WHERE id=?", (msg_id,)
            ).fetchone()
            if row:
                read_by = json.loads(row[0])
                if agent_name not in read_by:
                    read_by.append(agent_name)
                    self._conn.execute(
                        "UPDATE messages SET read_by_json=? WHERE id=?",
                        (json.dumps(read_by), msg_id),
                    )
        self._conn.commit()

    def _row_to_message(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "from_agent": row["from_agent"],
            "to": row["to"],
            "type": row["type"],
            "content": row["content"],
            "metadata": json.loads(row["metadata_json"]),
            "read_by": json.loads(row["read_by_json"]),
        }

    # ── Locks ─────────────────────────────────────────────────────

    def acquire_lock(self, agent: str, file_path: str, task_id: str = "") -> bool:
        try:
            self._conn.execute(
                "INSERT INTO locks (file_path, agent, acquired_at, task_id) VALUES (?, ?, ?, ?)",
                (file_path, agent, time.time(), task_id),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def release_lock(self, agent: str, file_path: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM locks WHERE file_path=? AND agent=?", (file_path, agent)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def check_lock(self, file_path: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM locks WHERE file_path=?", (file_path,)
        ).fetchone()
        if not row:
            return None
        return {"agent": row["agent"], "acquired_at": row["acquired_at"], "task_id": row["task_id"]}

    def list_locks(self) -> dict[str, dict]:
        rows = self._conn.execute("SELECT * FROM locks").fetchall()
        return {r["file_path"]: {"agent": r["agent"], "acquired_at": r["acquired_at"]} for r in rows}

    def release_all_locks(self, agent: str) -> list[str]:
        rows = self._conn.execute("SELECT file_path FROM locks WHERE agent=?", (agent,)).fetchall()
        released = [r["file_path"] for r in rows]
        self._conn.execute("DELETE FROM locks WHERE agent=?", (agent,))
        self._conn.commit()
        return released

    # ── Tasks ─────────────────────────────────────────────────────

    def create_task(self, subject: str, description: str = "", blocked_by: list[str] | None = None) -> dict:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = time.time()
        self._conn.execute(
            "INSERT INTO tasks (id, subject, description, status, created_at, blocked_by_json) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (task_id, subject, description, now, json.dumps(blocked_by or [])),
        )
        self._conn.commit()
        return {"id": task_id, "subject": subject, "description": description,
                "owner": None, "status": "pending", "created_at": now,
                "completed_at": None, "blocked_by": blocked_by or []}

    def get_tasks(self, pending_only: bool = False) -> list[dict]:
        if pending_only:
            rows = self._conn.execute("SELECT * FROM tasks WHERE status='pending'").fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
        return [self._row_to_task(r) for r in rows]

    def claim_task(self, task_id: str, agent: str) -> bool:
        cur = self._conn.execute(
            "UPDATE tasks SET owner=?, status='in_progress' WHERE id=? AND owner IS NULL",
            (agent, task_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def complete_task(self, task_id: str, agent: str) -> bool:
        cur = self._conn.execute(
            "UPDATE tasks SET status='completed', completed_at=? WHERE id=? AND owner=?",
            (time.time(), task_id, agent),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def _row_to_task(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"], "subject": row["subject"],
            "description": row["description"], "owner": row["owner"],
            "status": row["status"], "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "blocked_by": json.loads(row["blocked_by_json"]),
        }
