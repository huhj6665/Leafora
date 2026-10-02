# -*- coding: utf-8 -*-
"""SQLite 持久化出站队列与运行元数据。"""

import json
import os
import sqlite3
import threading
import time

from .protocol import utc_now


class PersistentStore(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)
        directory = os.path.dirname(self.path)
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._create_schema()

    def _create_schema(self):
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outbound (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    business_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    inspection_id TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(kind, business_id)
                );
                CREATE INDEX IF NOT EXISTS ix_outbound_pending
                    ON outbound(status, next_attempt_at, id);
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_id TEXT NOT NULL UNIQUE,
                    inspection_id TEXT NOT NULL,
                    data_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_images_pending
                    ON images(status, next_attempt_at, id);
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS command_evidence (
                    command_id TEXT NOT NULL,
                    phase_status TEXT NOT NULL,
                    ack_json TEXT NOT NULL,
                    PRIMARY KEY(command_id, phase_status)
                );
                """
            )
            # 老 SQLite 原位增列，不重建/清空队列；只在升级时回填一次。
            columns = [row["name"] for row in self._conn.execute("PRAGMA table_info(outbound)").fetchall()]
            if "inspection_id" not in columns:
                self._conn.execute("ALTER TABLE outbound ADD COLUMN inspection_id TEXT")
                for row in self._conn.execute("SELECT id,payload_json FROM outbound WHERE kind='data'").fetchall():
                    self._conn.execute("UPDATE outbound SET inspection_id=? WHERE id=?",
                                       (json.loads(row["payload_json"]).get("inspection_id"), row["id"]))
            self._conn.execute("CREATE INDEX IF NOT EXISTS ix_outbound_inspection ON outbound(kind,status,inspection_id)")

    def close(self):
        with self._lock:
            self._conn.close()

    def set_meta(self, key, value):
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (key, encoded),
            )

    def get_meta(self, key, default=None):
        with self._lock:
            row = self._conn.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return default

    def receive_command(self, payload):
        """MQTT 回调只持久化；执行留给单独工作线程。"""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO commands(command_id,payload_json) VALUES (?,?)",
                (payload["command_id"], json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
            )

    def pending_commands(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM commands WHERE status='pending' ORDER BY rowid LIMIT 20"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def command_result(self, command_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT result_json FROM commands WHERE command_id=?", (command_id,)
            ).fetchone()
        return json.loads(row["result_json"]) if row and row["result_json"] else None

    def commit_command(self, payload, ack, topic, active=None):
        """任务状态、幂等结果、待发送 ACK 在同一个事务中落盘。"""
        encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO commands(command_id,payload_json,result_json,status) VALUES (?,?,?,'done')",
                (payload["command_id"], encode(payload), encode(ack)),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO command_evidence(command_id,phase_status,ack_json) VALUES (?,?,?)",
                (ack["command_id"], ack["status"], encode(ack)),
            )
            if active is not None:
                self._conn.execute(
                    "INSERT OR REPLACE INTO metadata(key,value) VALUES ('active_inspection',?)", (encode(active),)
                )
            self._conn.execute(
                "INSERT OR IGNORE INTO outbound(kind,business_id,topic,payload_json,created_at) VALUES ('ack',?,?,?,?)",
                (ack["command_id"] + ":" + ack["status"], topic, encode(ack), utc_now()),
            )

    def replay_ack(self, ack, topic):
        self.enqueue_message("ack", ack["command_id"] + ":" + ack["status"], topic, ack)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbound SET status='pending',next_attempt_at=0 WHERE kind='ack' AND business_id=?",
                (ack["command_id"] + ":" + ack["status"],),
            )

    def command_evidence(self, command_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT ack_json FROM command_evidence WHERE command_id=? ORDER BY rowid", (command_id,)
            ).fetchall()
        return [json.loads(row["ack_json"]) for row in rows]

    def final_command_ids(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT command_id FROM command_evidence WHERE phase_status='COMPLETED'"
            ).fetchall()
        return [row["command_id"] for row in rows]

    def archive_inspection(self, active):
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('last_inspection',?)",
                               (json.dumps(active, ensure_ascii=False, separators=(",", ":")),))
            self._conn.execute("DELETE FROM metadata WHERE key='active_inspection'")

    def pending_business_count(self):
        with self._lock:
            data = self._conn.execute("SELECT COUNT(*) n FROM outbound WHERE kind='data' AND status='pending'").fetchone()["n"]
            images = self._conn.execute("SELECT COUNT(*) n FROM images WHERE status='pending'").fetchone()["n"]
        return int(data + images)

    def message_done(self, kind, business_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM outbound WHERE kind=? AND business_id=?", (kind, business_id)
            ).fetchone()
        return bool(row and row["status"] == "done")

    def commit_sample(self, active, topic, payload, image=None):
        """序号、摘要及数据/图片入队同时提交，END 不会看到半条采样。"""
        encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO outbound(kind,business_id,topic,payload_json,inspection_id,created_at) VALUES ('data',?,?,?,?,?)",
                (payload["data_id"], topic, encode(payload), payload["inspection_id"], utc_now()),
            )
            if image:
                self._conn.execute(
                    "INSERT OR IGNORE INTO images(image_id,inspection_id,data_id,captured_at,path,created_at) VALUES (?,?,?,?,?,?)",
                    (image["image_id"], active["inspection_id"], payload["data_id"],
                     image.get("captured_at") or payload["timestamp"], image["path"], utc_now()),
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES ('active_inspection',?)", (encode(active),)
            )

    def pending_data_for_inspection(self, inspection_id):
        """摘要只计业务数据和图片，ACK 本身不算待采样同步。"""
        with self._lock:
            count = self._conn.execute(
                "SELECT COUNT(*) n FROM outbound WHERE status='pending' AND kind='data' AND inspection_id=?", (inspection_id,)
            ).fetchone()["n"]
            count += self._conn.execute(
                "SELECT COUNT(*) n FROM images WHERE status='pending' AND inspection_id=?", (inspection_id,)
            ).fetchone()["n"]
        return int(count)

    def delete_meta(self, key):
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM metadata WHERE key=?", (key,))

    def enqueue_message(self, kind, business_id, topic, payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO outbound
                   (kind, business_id, topic, payload_json, inspection_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (kind, business_id, topic, encoded, payload.get("inspection_id"), utc_now()),
            )
            row = self._conn.execute(
                "SELECT id FROM outbound WHERE kind=? AND business_id=?",
                (kind, business_id),
            ).fetchone()
        return row["id"]

    def enqueue_image(self, image_id, inspection_id, data_id, captured_at, path):
        with self._lock, self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO images
                   (image_id, inspection_id, data_id, captured_at, path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (image_id, inspection_id, data_id, captured_at, os.path.abspath(path), utc_now()),
            )
            row = self._conn.execute(
                "SELECT id FROM images WHERE image_id=?", (image_id,)
            ).fetchone()
        return row["id"]

    def due_messages(self, limit=20):
        now = time.time()
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM outbound
                   WHERE status='pending' AND next_attempt_at<=?
                   ORDER BY id LIMIT ?""", (now, int(limit))
            ).fetchall()
        return [dict(row) for row in rows]

    def due_images(self, limit=5):
        now = time.time()
        with self._lock:
            rows = self._conn.execute(
                """SELECT images.* FROM images
                   WHERE images.status='pending' AND images.next_attempt_at<=?
                     AND EXISTS (
                         SELECT 1 FROM outbound
                         WHERE outbound.kind='data'
                           AND outbound.business_id=images.data_id
                           AND outbound.status='done'
                     )
                   ORDER BY images.id LIMIT ?""", (now, int(limit))
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_message_done(self, row_id):
        with self._lock, self._conn:
            self._conn.execute("UPDATE outbound SET status='done', last_error=NULL WHERE id=?", (row_id,))

    def mark_message_done_by_business(self, kind, business_id):
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE outbound SET status='done', last_error=NULL WHERE kind=? AND business_id=?",
                (kind, business_id),
            )

    def mark_image_done(self, row_id):
        with self._lock, self._conn:
            self._conn.execute("UPDATE images SET status='done', last_error=NULL WHERE id=?", (row_id,))

    @staticmethod
    def _delay(attempts):
        return min(60.0, float(2 ** min(max(attempts, 0), 6)))

    def fail_message(self, row_id, error):
        with self._lock, self._conn:
            row = self._conn.execute("SELECT attempts FROM outbound WHERE id=?", (row_id,)).fetchone()
            attempts = (row["attempts"] if row else 0) + 1
            self._conn.execute(
                """UPDATE outbound SET attempts=?, next_attempt_at=?, last_error=?
                   WHERE id=?""",
                (attempts, time.time() + self._delay(attempts), str(error)[:300], row_id),
            )

    def fail_image(self, row_id, error):
        with self._lock, self._conn:
            row = self._conn.execute("SELECT attempts FROM images WHERE id=?", (row_id,)).fetchone()
            attempts = (row["attempts"] if row else 0) + 1
            self._conn.execute(
                """UPDATE images SET attempts=?, next_attempt_at=?, last_error=?
                   WHERE id=?""",
                (attempts, time.time() + self._delay(attempts), str(error)[:300], row_id),
            )

    def retry_all(self):
        with self._lock, self._conn:
            self._conn.execute("UPDATE outbound SET next_attempt_at=0 WHERE status='pending'")
            self._conn.execute("UPDATE images SET next_attempt_at=0 WHERE status='pending'")

    def pending_counts(self):
        with self._lock:
            messages = self._conn.execute(
                "SELECT COUNT(*) AS n FROM outbound WHERE status='pending'"
            ).fetchone()["n"]
            images = self._conn.execute(
                "SELECT COUNT(*) AS n FROM images WHERE status='pending'"
            ).fetchone()["n"]
        return {"messages": int(messages), "images": int(images), "total": int(messages + images)}

    def pending_for_inspection(self, inspection_id):
        with self._lock:
            messages = self._conn.execute(
                """SELECT COUNT(*) AS n FROM outbound
                   WHERE status='pending' AND payload_json LIKE ?""",
                ('%"inspection_id":"{}"%'.format(inspection_id),),
            ).fetchone()["n"]
            images = self._conn.execute(
                "SELECT COUNT(*) AS n FROM images WHERE status='pending' AND inspection_id=?",
                (inspection_id,),
            ).fetchone()["n"]
        return int(messages + images)

    def cleanup_done(self, keep_recent=100):
        with self._lock, self._conn:
            self._conn.execute(
                """DELETE FROM outbound WHERE status='done' AND id NOT IN
                   (SELECT id FROM outbound WHERE status='done' ORDER BY id DESC LIMIT ?)""",
                (int(keep_recent),),
            )
            rows = self._conn.execute(
                """SELECT id, path FROM images WHERE status='done' AND id NOT IN
                   (SELECT id FROM images WHERE status='done' ORDER BY id DESC LIMIT ?)""",
                (int(keep_recent),),
            ).fetchall()
            for row in rows:
                try:
                    if os.path.isfile(row["path"]):
                        os.remove(row["path"])
                except OSError:
                    pass
                self._conn.execute("DELETE FROM images WHERE id=?", (row["id"],))

    def cleanup_completed_image_files(self):
        """清理崩溃发生在“SQLite 完成”与“删除文件”之间留下的临时图。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT path FROM images WHERE status='done'"
            ).fetchall()
        removed = 0
        for row in rows:
            try:
                if os.path.isfile(row["path"]):
                    os.remove(row["path"])
                    removed += 1
            except OSError:
                pass
        return removed
