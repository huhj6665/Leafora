"""Small durable outbox for virtual-device offline/retry verification."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutboxItem:
    kind: str
    business_id: str
    payload: dict


class PersistentOutbox:
    """SQLite outbox keyed by the original business ID.

    ``INSERT OR IGNORE`` guarantees that repeatedly caching the same sample,
    image metadata or control request does not allocate a new ID.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                kind TEXT NOT NULL,
                business_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (kind, business_id)
            )
            """
        )
        self.connection.execute("CREATE TABLE IF NOT EXISTS device_checkpoint (key TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
        self.connection.commit()

    def checkpoint(self, device_id: str, payload: dict, items: list[OutboxItem] = ()) -> None:
        """Persist generated objects and their sampling cursor in one commit."""
        with self.connection:
            for item in items:
                self.connection.execute(
                    "INSERT OR IGNORE INTO outbox(kind, business_id, payload_json) VALUES (?, ?, ?)",
                    (item.kind, item.business_id, json.dumps(item.payload, ensure_ascii=False, sort_keys=True)),
                )
            self.connection.execute(
                "INSERT INTO device_checkpoint(key, payload_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET payload_json=excluded.payload_json",
                (device_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            )

    def load_checkpoint(self, device_id: str) -> dict | None:
        row = self.connection.execute("SELECT payload_json FROM device_checkpoint WHERE key=?", (device_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def enqueue(self, kind: str, business_id: str, payload: dict) -> bool:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO outbox(kind, business_id, payload_json) VALUES (?, ?, ?)",
            (kind, business_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def items(self) -> list[OutboxItem]:
        rows = self.connection.execute(
            "SELECT kind, business_id, payload_json FROM outbox ORDER BY rowid"
        ).fetchall()
        return [OutboxItem(row[0], row[1], json.loads(row[2])) for row in rows]

    def acknowledge(self, kind: str, business_id: str) -> None:
        self.connection.execute(
            "DELETE FROM outbox WHERE kind = ? AND business_id = ?",
            (kind, business_id),
        )
        self.connection.commit()

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM outbox").fetchone()[0])

    def business_count(self, inspection_id: str | None = None) -> int:
        return sum(1 for item in self.items() if item.kind != "ack"
                   and (inspection_id is None or item.payload.get("inspection_id") == inspection_id))

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "PersistentOutbox":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
