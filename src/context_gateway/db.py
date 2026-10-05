from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any

from .normalize import extract_messages, make_record, messages_from_indexed_text, stable_hash


SCHEMA_VERSION = 6

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projects(
    project_uid TEXT PRIMARY KEY,
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    provider TEXT NOT NULL,
    account_id TEXT NOT NULL,
    source TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    UNIQUE(provider, account_id, id)
);

CREATE INDEX IF NOT EXISTS idx_projects_provider_account
    ON projects(provider, account_id);

CREATE TABLE IF NOT EXISTS conversations(
    conversation_uid TEXT PRIMARY KEY,
    id TEXT NOT NULL,
    project_uid TEXT,
    project_id TEXT,
    project_name TEXT,
    title TEXT,
    create_time REAL,
    update_time REAL,
    raw_path TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    indexed_text TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    provider TEXT NOT NULL,
    account_id TEXT NOT NULL,
    source TEXT NOT NULL,
    UNIQUE(provider, account_id, id)
);

CREATE INDEX IF NOT EXISTS idx_conv_project
    ON conversations(project_uid);

CREATE INDEX IF NOT EXISTS idx_conv_provider_account
    ON conversations(provider, account_id);

CREATE TABLE IF NOT EXISTS conversation_snapshots(
    snapshot_id TEXT PRIMARY KEY,
    conversation_uid TEXT NOT NULL,
    snapshot_seq INTEGER NOT NULL,
    captured_at REAL NOT NULL,
    source_updated_at REAL,
    raw_path TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    completeness_status TEXT NOT NULL DEFAULT 'complete',
    completeness_reason TEXT,
    UNIQUE(conversation_uid, snapshot_seq),
    UNIQUE(conversation_uid, raw_hash)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_conversation
    ON conversation_snapshots(conversation_uid, snapshot_seq);

CREATE TABLE IF NOT EXISTS snapshot_observations(
    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL,
    observed_at REAL NOT NULL,
    ingested_at REAL NOT NULL,
    source_created_at REAL,
    source_updated_at REAL,
    acquisition_method TEXT NOT NULL,
    completeness_status TEXT NOT NULL DEFAULT 'complete',
    completeness_reason TEXT,
    acquisition_attempt_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_snapshot_observations_snapshot
    ON snapshot_observations(snapshot_id, observed_at);

CREATE INDEX IF NOT EXISTS idx_snapshot_observations_fresh
    ON snapshot_observations(snapshot_id, observed_at, completeness_status);

CREATE TABLE IF NOT EXISTS conversation_current(
    conversation_uid TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    current_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS acquisition_checkpoints(
    provider TEXT NOT NULL,
    account_id TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL,
    cursor TEXT,
    last_success_at REAL,
    last_seen_remote_at REAL,
    last_error TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY(provider, account_id, scope_type, scope_id, method)
);

CREATE INDEX IF NOT EXISTS idx_acquisition_checkpoints_scope
    ON acquisition_checkpoints(provider, account_id, scope_type, scope_id);

CREATE TABLE IF NOT EXISTS host_session_bindings(
    provider TEXT NOT NULL,
    host_session_fingerprint TEXT NOT NULL,
    account_id TEXT NOT NULL,
    conversation_uid TEXT NOT NULL,
    bound_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY(provider, host_session_fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_host_session_binding_conversation
    ON host_session_bindings(conversation_uid);

CREATE TABLE IF NOT EXISTS context_handoffs(
    handoff_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    account_id TEXT NOT NULL,
    conversation_uid TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    host_session_fingerprint TEXT NOT NULL,
    consumer_session_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    consumed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_context_handoffs_expiry
    ON context_handoffs(expires_at);

CREATE TABLE IF NOT EXISTS messages(
    message_uid TEXT PRIMARY KEY,
    conversation_uid TEXT NOT NULL,
    id TEXT NOT NULL,
    role TEXT NOT NULL,
    latest_text TEXT NOT NULL,
    latest_content_hash TEXT NOT NULL,
    create_time REAL,
    latest_snapshot_id TEXT,
    UNIQUE(conversation_uid, id)
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_uid);

CREATE TABLE IF NOT EXISTS snapshot_messages(
    snapshot_id TEXT NOT NULL,
    message_uid TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    parent_message_uid TEXT,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    create_time REAL,
    PRIMARY KEY(snapshot_id, message_uid)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_messages_order
    ON snapshot_messages(snapshot_id, ordinal);

CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
    message_uid UNINDEXED,
    snapshot_id UNINDEXED,
    conversation_uid UNINDEXED,
    conversation_id UNINDEXED,
    project_name,
    title,
    role,
    content
);
"""


def scoped_uid(kind: str, provider: str, account_id: str, external_id: str) -> str:
    raw = f"{kind}\0{provider}\0{account_id}\0{external_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def snapshot_uid(conversation_uid: str, seq: int) -> str:
    return f"{conversation_uid}:snapshot-{seq:06d}"


def message_uid_for(conversation_uid: str, provider_message_id: str) -> str:
    raw = f"message\0{conversation_uid}\0{provider_message_id}".encode()
    return hashlib.sha256(raw).hexdigest()


class ArchiveDB:
    def __init__(self, path: Path, check_same_thread: bool = False):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=check_same_thread)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._prepare_schema()

    def _prepare_schema(self) -> None:
        self.conn.execute("PRAGMA journal_mode=WAL")
        if self._has_legacy_schema():
            self._migrate_legacy()
        else:
            self.conn.executescript(SCHEMA)
        self._upgrade_schema()
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.conn.commit()

    def _upgrade_schema(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(conversation_snapshots)")
        }
        if "completeness_status" not in columns:
            self.conn.execute(
                "ALTER TABLE conversation_snapshots ADD COLUMN completeness_status TEXT NOT NULL DEFAULT 'complete'"
            )
        if "completeness_reason" not in columns:
            self.conn.execute(
                "ALTER TABLE conversation_snapshots ADD COLUMN completeness_reason TEXT"
            )
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshot_observations(
                observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL,
                observed_at REAL NOT NULL,
                ingested_at REAL NOT NULL,
                source_created_at REAL,
                source_updated_at REAL,
                acquisition_method TEXT NOT NULL,
                completeness_status TEXT NOT NULL DEFAULT 'complete',
                completeness_reason TEXT,
                acquisition_attempt_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_snapshot_observations_snapshot
                ON snapshot_observations(snapshot_id, observed_at);
            CREATE INDEX IF NOT EXISTS idx_snapshot_observations_fresh
                ON snapshot_observations(snapshot_id, observed_at, completeness_status);
            """
        )
        existing = self.conn.execute(
            "SELECT COUNT(*) AS n FROM snapshot_observations"
        ).fetchone()
        if existing and int(existing["n"]) == 0:
            self.conn.execute(
                """
                INSERT INTO snapshot_observations(
                    snapshot_id, observed_at, ingested_at,
                    source_created_at, source_updated_at,
                    acquisition_method, completeness_status, completeness_reason
                )
                SELECT s.snapshot_id,
                       s.captured_at,
                       s.captured_at,
                       c.create_time,
                       s.source_updated_at,
                       COALESCE(c.source, 'migration'),
                       COALESCE(s.completeness_status, 'complete'),
                       s.completeness_reason
                FROM conversation_snapshots s
                JOIN conversations c ON c.conversation_uid=s.conversation_uid
                """
            )

    def _has_legacy_schema(self) -> bool:
        tables = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "conversations" not in tables:
            return False
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(conversations)")
        }
        return "conversation_uid" not in columns

    def _migrate_legacy(self) -> None:
        legacy_projects = "legacy_projects_migration"
        legacy_conversations = "legacy_conversations_migration"

        self.conn.execute(f"ALTER TABLE projects RENAME TO {legacy_projects}")
        self.conn.execute(f"ALTER TABLE conversations RENAME TO {legacy_conversations}")
        self.conn.execute("DROP TABLE IF EXISTS conversation_fts")
        self.conn.executescript(SCHEMA)

        project_rows = list(
            self.conn.execute(f"SELECT * FROM {legacy_projects}")
        )
        for row in project_rows:
            provider = row["provider"] if "provider" in row.keys() else "chatgpt"
            account_id = row["account_id"] if "account_id" in row.keys() else "default"
            project_id = row["id"]
            project_uid = scoped_uid("project", provider, account_id, project_id)
            self.conn.execute(
                """INSERT OR IGNORE INTO projects
                   (project_uid,id,name,created_at,updated_at,provider,account_id,source,raw_json)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    project_uid,
                    project_id,
                    row["name"],
                    row["created_at"],
                    row["updated_at"],
                    provider,
                    account_id,
                    row["source"] if "source" in row.keys() else provider,
                    row["raw_json"],
                ),
            )

        conv_rows = list(
            self.conn.execute(f"SELECT * FROM {legacy_conversations}")
        )
        for row in conv_rows:
            provider = row["provider"] if "provider" in row.keys() else "chatgpt"
            account_id = row["account_id"] if "account_id" in row.keys() else "default"
            source = row["source"] if "source" in row.keys() else provider
            conversation_id = row["id"]
            conversation_uid = scoped_uid(
                "conversation", provider, account_id, conversation_id
            )
            project_id = row["project_id"]
            project_uid = (
                scoped_uid("project", provider, account_id, project_id)
                if project_id
                else None
            )
            raw_json = row["raw_json"]
            try:
                payload = json.loads(raw_json)
            except Exception:
                payload = {"id": conversation_id, "title": row["title"]}
            messages = extract_messages(payload)
            if not messages:
                messages = messages_from_indexed_text(row["indexed_text"])

            self.conn.execute(
                """INSERT OR IGNORE INTO conversations
                   (conversation_uid,id,project_uid,project_id,project_name,title,create_time,update_time,
                    raw_path,raw_hash,indexed_text,raw_json,provider,account_id,source)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    conversation_uid,
                    conversation_id,
                    project_uid,
                    project_id,
                    row["project_name"],
                    row["title"],
                    row["create_time"],
                    row["update_time"],
                    row["raw_path"],
                    row["raw_hash"],
                    row["indexed_text"],
                    raw_json,
                    provider,
                    account_id,
                    source,
                ),
            )

            captured_at = float(row["update_time"] or row["create_time"] or time.time())
            snapshot_id = snapshot_uid(conversation_uid, 1)
            self.conn.execute(
                """INSERT OR IGNORE INTO conversation_snapshots
                   (snapshot_id,conversation_uid,snapshot_seq,captured_at,source_updated_at,raw_path,raw_hash,message_count)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    conversation_uid,
                    1,
                    captured_at,
                    row["update_time"],
                    row["raw_path"],
                    row["raw_hash"],
                    len(messages),
                ),
            )
            self._insert_messages(
                conversation_uid=conversation_uid,
                snapshot_id=snapshot_id,
                conversation_id=conversation_id,
                project_name=row["project_name"],
                title=row["title"],
                provider=provider,
                account_id=account_id,
                messages=messages,
            )
            self.conn.execute(
                """INSERT OR REPLACE INTO conversation_current
                   (conversation_uid,snapshot_id,current_at)
                   VALUES(?,?,?)""",
                (conversation_uid, snapshot_id, captured_at),
            )

        self.conn.execute(f"DROP TABLE {legacy_projects}")
        self.conn.execute(f"DROP TABLE {legacy_conversations}")

    def _insert_messages(
        self,
        conversation_uid: str,
        snapshot_id: str,
        conversation_id: str,
        project_name: str,
        title: str,
        provider: str,
        account_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        self.conn.execute(
            "DELETE FROM message_fts WHERE snapshot_id=?",
            (snapshot_id,),
        )
        for item in messages:
            provider_message_id = item["provider_message_id"]
            msg_uid = message_uid_for(conversation_uid, provider_message_id)
            text = item["text"]
            content_hash = stable_hash(text)
            parent_uid = (
                message_uid_for(conversation_uid, item["parent_message_id"])
                if item.get("parent_message_id")
                else None
            )
            self.conn.execute(
                """INSERT INTO messages
                   (message_uid,conversation_uid,id,role,latest_text,latest_content_hash,create_time,latest_snapshot_id)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(message_uid) DO UPDATE SET
                     latest_text=excluded.latest_text,
                     latest_content_hash=excluded.latest_content_hash,
                     create_time=excluded.create_time,
                     latest_snapshot_id=excluded.latest_snapshot_id""",
                (
                    msg_uid,
                    conversation_uid,
                    provider_message_id,
                    item["role"],
                    text,
                    content_hash,
                    item.get("create_time"),
                    snapshot_id,
                ),
            )
            self.conn.execute(
                """INSERT OR REPLACE INTO snapshot_messages
                   (snapshot_id,message_uid,ordinal,parent_message_uid,role,text,content_hash,create_time)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    msg_uid,
                    item["ordinal"],
                    parent_uid,
                    item["role"],
                    text,
                    content_hash,
                    item.get("create_time"),
                ),
            )
            self.conn.execute(
                """INSERT INTO message_fts
                   (message_uid,snapshot_id,conversation_uid,conversation_id,project_name,title,role,content)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    msg_uid,
                    snapshot_id,
                    conversation_uid,
                    conversation_id,
                    project_name,
                    title,
                    item["role"],
                    text,
                ),
            )

    def bind_host_session(
        self,
        *,
        provider: str,
        host_session_fingerprint: str,
        account_id: str,
        conversation_uid: str,
        source: str = "explicit",
        now: float | None = None,
    ) -> dict[str, Any]:
        if not host_session_fingerprint.strip():
            raise ValueError("host_session_fingerprint is required")
        if not account_id.strip():
            raise ValueError("account_id is required")
        if not conversation_uid.strip():
            raise ValueError("conversation_uid is required")

        conversation = self.get(conversation_uid)
        if not conversation:
            raise ValueError(f"conversation not found: {conversation_uid}")
        if str(conversation.get("provider") or "") != provider:
            raise ValueError("binding provider does not match conversation provider")
        if str(conversation.get("account_id") or "") != account_id:
            raise ValueError("binding account does not match conversation account")

        observed_at = float(now if now is not None else time.time())
        existing = self.conn.execute(
            """SELECT * FROM host_session_bindings
               WHERE provider=? AND host_session_fingerprint=?""",
            (provider, host_session_fingerprint),
        ).fetchone()
        if existing and str(existing["conversation_uid"]) != conversation_uid:
            raise ValueError(
                "host session is already bound to a different conversation; explicit rebinding is required"
            )

        bound_at = float(existing["bound_at"]) if existing else observed_at
        self.conn.execute(
            """INSERT INTO host_session_bindings
               (provider, host_session_fingerprint, account_id, conversation_uid,
                bound_at, last_seen_at, source)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(provider, host_session_fingerprint) DO UPDATE SET
                 account_id=excluded.account_id,
                 conversation_uid=excluded.conversation_uid,
                 last_seen_at=excluded.last_seen_at,
                 source=excluded.source""",
            (
                provider,
                host_session_fingerprint,
                account_id,
                conversation_uid,
                bound_at,
                observed_at,
                source,
            ),
        )
        self.conn.commit()
        return self.get_host_session_binding(
            provider,
            host_session_fingerprint,
            touch=False,
        ) or {}

    def get_host_session_binding(
        self,
        provider: str,
        host_session_fingerprint: str,
        *,
        touch: bool = True,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT provider, host_session_fingerprint, account_id,
                      conversation_uid, bound_at, last_seen_at, source
               FROM host_session_bindings
               WHERE provider=? AND host_session_fingerprint=?""",
            (provider, host_session_fingerprint),
        ).fetchone()
        if not row:
            return None
        if touch:
            observed_at = float(now if now is not None else time.time())
            self.conn.execute(
                """UPDATE host_session_bindings
                   SET last_seen_at=?
                   WHERE provider=? AND host_session_fingerprint=?""",
                (observed_at, provider, host_session_fingerprint),
            )
            self.conn.commit()
            row = self.conn.execute(
                """SELECT provider, host_session_fingerprint, account_id,
                          conversation_uid, bound_at, last_seen_at, source
                   FROM host_session_bindings
                   WHERE provider=? AND host_session_fingerprint=?""",
                (provider, host_session_fingerprint),
            ).fetchone()
        return dict(row) if row else None

    def create_context_handoff(
        self,
        *,
        provider: str,
        host_session_fingerprint: str,
        consumer_session_id: str,
        conversation_uid: str | None = None,
        snapshot_id: str | None = None,
        ttl_seconds: int = 120,
        now: float | None = None,
    ) -> dict[str, Any]:
        if not host_session_fingerprint.strip():
            raise ValueError("host_session_fingerprint is required")
        if not consumer_session_id.strip():
            raise ValueError("consumer_session_id is required")
        ttl = max(5, min(int(ttl_seconds), 900))
        created_at = float(now if now is not None else time.time())
        binding = self.get_host_session_binding(
            provider,
            host_session_fingerprint,
            touch=True,
            now=created_at,
        )
        if conversation_uid:
            if binding and binding["conversation_uid"] != conversation_uid:
                raise ValueError(
                    "handoff conversation does not match the current host-session binding"
                )
        elif binding:
            conversation_uid = str(binding["conversation_uid"])
        else:
            raise ValueError("current host session is not bound to a conversation")

        conversation = self.get(str(conversation_uid))
        if not conversation:
            raise ValueError(f"conversation not found: {conversation_uid}")
        if str(conversation.get("provider") or "") != provider:
            raise ValueError("handoff provider does not match conversation provider")
        if binding and str(binding.get("account_id") or "") != str(conversation.get("account_id") or ""):
            raise ValueError("handoff account does not match conversation account")

        if snapshot_id:
            snapshot = self.get_snapshot(str(snapshot_id))
            if not snapshot or str(snapshot.get("conversation_uid")) != str(conversation_uid):
                raise ValueError("handoff snapshot does not belong to the conversation")
            if str(snapshot.get("completeness_status") or "complete") != "complete":
                raise ValueError("handoff cannot pin an incomplete snapshot")
        else:
            snapshot = self.current_snapshot(str(conversation_uid))
            if not snapshot:
                raise ValueError(f"current snapshot not found: {conversation_uid}")

        handoff_id = secrets.token_urlsafe(32)
        expires_at = created_at + ttl
        account_id = str(conversation.get("account_id") or "")
        self.conn.execute(
            """DELETE FROM context_handoffs WHERE expires_at < ?""",
            (created_at,),
        )
        self.conn.execute(
            """INSERT INTO context_handoffs
               (handoff_id, provider, account_id, conversation_uid, snapshot_id,
                host_session_fingerprint, consumer_session_id, created_at, expires_at, consumed_at)
               VALUES(?,?,?,?,?,?,?,?,?,NULL)""",
            (
                handoff_id,
                provider,
                account_id,
                str(conversation_uid),
                str(snapshot["snapshot_id"]),
                host_session_fingerprint,
                consumer_session_id,
                created_at,
                expires_at,
            ),
        )
        self.conn.commit()
        return {
            "handoff_id": handoff_id,
            "provider": provider,
            "account_id": account_id,
            "conversation_uid": str(conversation_uid),
            "snapshot_id": str(snapshot["snapshot_id"]),
            "created_at": created_at,
            "expires_at": expires_at,
            "consumer_session_id": consumer_session_id,
        }

    def redeem_context_handoff(
        self,
        handoff_id: str,
        *,
        consumer_session_id: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        if not handoff_id.strip():
            raise ValueError("handoff_id is required")
        observed_at = float(now if now is not None else time.time())
        row = self.conn.execute(
            """SELECT * FROM context_handoffs WHERE handoff_id=?""",
            (handoff_id,),
        ).fetchone()
        if not row:
            raise ValueError("handoff not found")
        if row["consumed_at"] is not None:
            raise ValueError("handoff already consumed")
        if observed_at >= float(row["expires_at"]):
            self.conn.execute(
                "DELETE FROM context_handoffs WHERE handoff_id=? AND consumed_at IS NULL",
                (handoff_id,),
            )
            self.conn.commit()
            raise ValueError("handoff expired")
        if consumer_session_id and str(row["consumer_session_id"]) != consumer_session_id:
            raise ValueError("handoff consumer session does not match")
        cur = self.conn.execute(
            """UPDATE context_handoffs
               SET consumed_at=?
               WHERE handoff_id=? AND consumed_at IS NULL""",
            (observed_at, handoff_id),
        )
        if cur.rowcount != 1:
            self.conn.rollback()
            raise ValueError("handoff already consumed")
        self.conn.commit()
        consumed = self.conn.execute(
            "SELECT * FROM context_handoffs WHERE handoff_id=?",
            (handoff_id,),
        ).fetchone()
        return dict(consumed) if consumed else dict(row)

    def close(self):
        self.conn.close()

    def upsert_project(self, p: dict[str, Any]):
        provider = p.get("provider", "chatgpt")
        account_id = p.get("account_id", "default")
        project_id = str(p["id"])
        project_uid = scoped_uid("project", provider, account_id, project_id)
        self.conn.execute(
            """INSERT INTO projects
               (project_uid,id,name,created_at,updated_at,provider,account_id,source,raw_json)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(project_uid) DO UPDATE SET
                 id=excluded.id,name=excluded.name,created_at=excluded.created_at,updated_at=excluded.updated_at,
                 provider=excluded.provider,account_id=excluded.account_id,source=excluded.source,raw_json=excluded.raw_json""",
            (
                project_uid,
                project_id,
                p.get("name") or "",
                p.get("created_at"),
                p.get("updated_at"),
                provider,
                account_id,
                p.get("source", provider),
                json.dumps(p, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def _conversation_uid_from_record(self, c: dict[str, Any]) -> str:
        return scoped_uid(
            "conversation",
            c.get("provider", "chatgpt"),
            c.get("account_id", "default"),
            str(c["id"]),
        )

    def next_snapshot_seq(self, c: dict[str, Any]) -> int:
        uid = self._conversation_uid_from_record(c)
        row = self.conn.execute(
            "SELECT COALESCE(MAX(snapshot_seq),0)+1 AS next_seq FROM conversation_snapshots WHERE conversation_uid=?",
            (uid,),
        ).fetchone()
        return int(row["next_seq"])

    def current_snapshot(self, conversation_uid: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT s.*, c.id AS conversation_id, c.provider, c.account_id,
                      cc.current_at AS last_observed_at
               FROM conversation_current cc
               JOIN conversation_snapshots s ON s.snapshot_id=cc.snapshot_id
               JOIN conversations c ON c.conversation_uid=cc.conversation_uid
               WHERE cc.conversation_uid=?""",
            (conversation_uid,),
        ).fetchone()
        return dict(row) if row else None

    def current_snapshot_for_record(self, c: dict[str, Any]) -> dict[str, Any] | None:
        return self.current_snapshot(self._conversation_uid_from_record(c))

    def upsert_conversation(
        self,
        c: dict[str, Any],
        *,
        promote_current: bool = True,
    ):
        provider = c.get("provider", "chatgpt")
        account_id = c.get("account_id", "default")
        conversation_id = str(c["id"])
        conversation_uid = self._conversation_uid_from_record(c)

        project_id = c.get("project_id")
        project_uid = (
            scoped_uid("project", provider, account_id, str(project_id))
            if project_id
            else None
        )

        self.conn.execute(
            """INSERT INTO conversations
               (conversation_uid,id,project_uid,project_id,project_name,title,create_time,update_time,
                raw_path,raw_hash,indexed_text,raw_json,provider,account_id,source)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(conversation_uid) DO UPDATE SET
                 project_uid=excluded.project_uid,project_id=excluded.project_id,project_name=excluded.project_name,
                 title=excluded.title,create_time=excluded.create_time,update_time=excluded.update_time,
                 raw_path=excluded.raw_path,raw_hash=excluded.raw_hash,indexed_text=excluded.indexed_text,
                 raw_json=excluded.raw_json,provider=excluded.provider,account_id=excluded.account_id,source=excluded.source""",
            (
                conversation_uid,
                conversation_id,
                project_uid,
                project_id,
                c.get("project_name"),
                c.get("title") or "Untitled",
                c.get("create_time"),
                c.get("update_time"),
                c["raw_path"],
                c["raw_hash"],
                c.get("indexed_text", ""),
                c.get("raw_json", "{}"),
                provider,
                account_id,
                c.get("source", provider),
            ),
        )

        existing = self.conn.execute(
            """SELECT snapshot_id FROM conversation_snapshots
               WHERE conversation_uid=? AND raw_hash=?""",
            (conversation_uid, c["raw_hash"]),
        ).fetchone()

        observed_at = float(
            c.get("observed_at")
            or c.get("captured_at")
            or time.time()
        )
        ingested_at = float(c.get("ingested_at") or time.time())
        completeness_status = str(
            c.get("snapshot_completeness_status")
            or ("complete" if promote_current else "partial")
        )
        completeness_reason = c.get("snapshot_completeness_reason")
        acquisition_method = str(c.get("acquisition_method") or c.get("source") or provider)
        source_created_at = c.get("create_time")
        source_updated_at = c.get("update_time")

        if existing:
            snapshot_id = existing["snapshot_id"]
            existing_snapshot = self.conn.execute(
                "SELECT raw_path FROM conversation_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            if existing_snapshot:
                self.conn.execute(
                    "UPDATE conversations SET raw_path=? WHERE conversation_uid=?",
                    (existing_snapshot["raw_path"], conversation_uid),
                )
            self.conn.execute(
                """UPDATE conversation_snapshots
                   SET completeness_status=?,
                       completeness_reason=?
                   WHERE snapshot_id=?""",
                (completeness_status, completeness_reason, snapshot_id),
            )
        else:
            snapshot_seq = self.next_snapshot_seq(c)
            snapshot_id = snapshot_uid(conversation_uid, snapshot_seq)
            messages = c.get("messages") or []
            if not messages:
                try:
                    messages = extract_messages(json.loads(c.get("raw_json", "{}")))
                except Exception:
                    messages = []
            if not messages:
                messages = messages_from_indexed_text(c.get("indexed_text", ""))
            self.conn.execute(
                """INSERT INTO conversation_snapshots
                   (snapshot_id,conversation_uid,snapshot_seq,captured_at,source_updated_at,
                    raw_path,raw_hash,message_count,completeness_status,completeness_reason)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    conversation_uid,
                    snapshot_seq,
                    observed_at,
                    source_updated_at,
                    c["raw_path"],
                    c["raw_hash"],
                    len(messages),
                    completeness_status,
                    completeness_reason,
                ),
            )
            self._insert_messages(
                conversation_uid=conversation_uid,
                snapshot_id=snapshot_id,
                conversation_id=conversation_id,
                project_name=c.get("project_name") or "",
                title=c.get("title") or "Untitled",
                provider=provider,
                account_id=account_id,
                messages=messages,
            )

        self.conn.execute(
            """INSERT INTO snapshot_observations(
                   snapshot_id,observed_at,ingested_at,source_created_at,source_updated_at,
                   acquisition_method,completeness_status,completeness_reason,acquisition_attempt_id
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                snapshot_id,
                observed_at,
                ingested_at,
                source_created_at,
                source_updated_at,
                acquisition_method,
                completeness_status,
                completeness_reason,
                c.get("acquisition_attempt_id"),
            ),
        )

        # Only complete observations may advance the current trusted pointer.
        if promote_current and completeness_status == "complete":
            self.conn.execute(
                """INSERT INTO conversation_current(conversation_uid,snapshot_id,current_at)
                   VALUES(?,?,?)
                   ON CONFLICT(conversation_uid) DO UPDATE SET
                     snapshot_id=excluded.snapshot_id,current_at=excluded.current_at""",
                (conversation_uid, snapshot_id, observed_at),
            )

        self.conn.commit()
        return {
            "conversation_uid": conversation_uid,
            "snapshot_id": snapshot_id,
            "promoted_current": bool(promote_current and completeness_status == "complete"),
            "snapshot": self.current_snapshot(conversation_uid),
        }

    def upsert_acquisition_checkpoint(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        now = float(checkpoint.get("updated_at") or time.time())
        self.conn.execute(
            """INSERT INTO acquisition_checkpoints
               (provider,account_id,scope_type,scope_id,method,status,cursor,
                last_success_at,last_seen_remote_at,last_error,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(provider,account_id,scope_type,scope_id,method) DO UPDATE SET
                 status=excluded.status,
                 cursor=excluded.cursor,
                 last_success_at=excluded.last_success_at,
                 last_seen_remote_at=excluded.last_seen_remote_at,
                 last_error=excluded.last_error,
                 updated_at=excluded.updated_at""",
            (
                checkpoint["provider"],
                checkpoint.get("account_id", "default"),
                checkpoint["scope_type"],
                checkpoint["scope_id"],
                checkpoint["method"],
                checkpoint.get("status", "unknown"),
                checkpoint.get("cursor"),
                checkpoint.get("last_success_at"),
                checkpoint.get("last_seen_remote_at"),
                checkpoint.get("last_error"),
                now,
            ),
        )
        self.conn.commit()
        return self.get_acquisition_checkpoint(
            checkpoint["provider"],
            checkpoint.get("account_id", "default"),
            checkpoint["scope_type"],
            checkpoint["scope_id"],
            checkpoint["method"],
        ) or {}

    def get_acquisition_checkpoint(
        self,
        provider: str,
        account_id: str,
        scope_type: str,
        scope_id: str,
        method: str,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT provider,account_id,scope_type,scope_id,method,status,cursor,
                      last_success_at,last_seen_remote_at,last_error,updated_at
               FROM acquisition_checkpoints
               WHERE provider=? AND account_id=? AND scope_type=? AND scope_id=? AND method=?""",
            (provider, account_id, scope_type, scope_id, method),
        ).fetchone()
        return dict(row) if row else None

    def projects(self):
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT project_uid,id,name,created_at,updated_at,provider,account_id,source
                   FROM projects ORDER BY name"""
            )
        ]

    def conversations(self, project_id=None, provider=None, account_id=None):
        q = """SELECT c.conversation_uid,c.id,c.project_uid,c.project_id,c.project_name,c.title,
                      c.create_time,c.update_time,c.raw_path,c.raw_hash,c.provider,c.account_id,c.source,
                      cc.snapshot_id AS current_snapshot_id
               FROM conversations c
               LEFT JOIN conversation_current cc ON cc.conversation_uid=c.conversation_uid"""
        clauses: list[str] = []
        args: list[Any] = []
        if project_id:
            project_uids = [
                row["project_uid"]
                for row in self.conn.execute(
                    "SELECT project_uid FROM projects WHERE project_uid=? OR id=?",
                    (project_id, project_id),
                )
            ]
            if project_uids:
                clauses.append("c.project_uid IN (" + ",".join("?" for _ in project_uids) + ")")
                args.extend(project_uids)
            else:
                clauses.append("c.project_id=?")
                args.append(project_id)
        if provider:
            clauses.append("c.provider=?")
            args.append(provider)
        if account_id:
            clauses.append("c.account_id=?")
            args.append(account_id)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY COALESCE(c.update_time,c.create_time) DESC"
        return [dict(r) for r in self.conn.execute(q, args)]

    def _resolve_conversation_uid(self, cid: str) -> str:
        row = self.conn.execute(
            "SELECT conversation_uid FROM conversations WHERE conversation_uid=?",
            (cid,),
        ).fetchone()
        if row:
            return row["conversation_uid"]

        rows = list(
            self.conn.execute(
                "SELECT conversation_uid FROM conversations WHERE id=?",
                (cid,),
            )
        )
        if len(rows) == 1:
            return rows[0]["conversation_uid"]
        if len(rows) > 1:
            raise ValueError(
                f"conversation id '{cid}' is ambiguous across provider/account scopes; use conversation_uid"
            )
        return cid

    def get(self, cid):
        uid = self._resolve_conversation_uid(cid)
        row = self.conn.execute(
            "SELECT * FROM conversations WHERE conversation_uid=?",
            (uid,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        snapshot = self.current_snapshot(uid)
        item["current_snapshot"] = snapshot
        if snapshot:
            item["messages"] = [
                dict(r)
                for r in self.conn.execute(
                    """SELECT sm.message_uid,m.id AS message_id,m.role,sm.ordinal,sm.text,
                              sm.content_hash,sm.create_time
                       FROM snapshot_messages sm
                       JOIN messages m ON m.message_uid=sm.message_uid
                       WHERE sm.snapshot_id=?
                       ORDER BY sm.ordinal""",
                    (snapshot["snapshot_id"],),
                )
            ]
        else:
            item["messages"] = []
        return item

    def get_snapshot(self, snapshot_id: str):
        row = self.conn.execute(
            """SELECT s.*,c.id AS conversation_id,c.project_id,c.project_name,c.title,
                      c.provider,c.account_id,c.source,
                      (SELECT MAX(so.observed_at)
                       FROM snapshot_observations so
                       WHERE so.snapshot_id=s.snapshot_id
                         AND so.completeness_status='complete') AS last_observed_at
               FROM conversation_snapshots s
               JOIN conversations c ON c.conversation_uid=s.conversation_uid
               WHERE s.snapshot_id=?""",
            (snapshot_id,),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["messages"] = [
            dict(r)
            for r in self.conn.execute(
                """SELECT sm.message_uid,m.id AS message_id,sm.ordinal,sm.parent_message_uid,
                          sm.role,sm.text,sm.content_hash,sm.create_time
                   FROM snapshot_messages sm
                   JOIN messages m ON m.message_uid=sm.message_uid
                   WHERE sm.snapshot_id=?
                   ORDER BY sm.ordinal""",
                (snapshot_id,),
            )
        ]
        return item

    def snapshots(self, conversation_id: str):
        uid = self._resolve_conversation_uid(conversation_id)
        return [
            dict(r)
            for r in self.conn.execute(
                """SELECT * FROM conversation_snapshots
                   WHERE conversation_uid=? ORDER BY snapshot_seq""",
                (uid,),
            )
        ]

    def search_messages(
        self,
        q: str,
        limit: int = 20,
        project_id: str | None = None,
        provider: str | None = None,
        account_id: str | None = None,
        snapshot_id: str | None = None,
        current_only: bool = True,
        exclude_conversation_uids: list[str] | tuple[str, ...] | None = None,
        min_captured_at: float | None = None,
    ):
        limit = max(1, min(int(limit), 50))
        sql = """SELECT
                    f.*,
                    m.id AS message_id,
                    c.id AS id,c.project_id,c.project_name,c.title,c.update_time,c.create_time,
                    c.provider,c.account_id,c.source,
                    s.snapshot_seq,s.captured_at,s.source_updated_at,s.raw_path,s.raw_hash,
                    (SELECT current_at FROM conversation_current WHERE snapshot_id=s.snapshot_id) AS last_observed_at,
                    bm25(message_fts) AS score
                 FROM message_fts f
                 JOIN messages m ON m.message_uid=f.message_uid
                 JOIN conversations c ON c.conversation_uid=f.conversation_uid
                 JOIN conversation_snapshots s ON s.snapshot_id=f.snapshot_id"""
        args: list[Any] = []
        clauses: list[str] = []

        if current_only and not snapshot_id:
            sql += " JOIN conversation_current cc ON cc.snapshot_id=f.snapshot_id"
        if q:
            clauses.append("message_fts MATCH ?")
            args.append(q)
        if snapshot_id:
            clauses.append("f.snapshot_id=?")
            args.append(snapshot_id)

        excluded = [str(x) for x in (exclude_conversation_uids or ()) if str(x)]
        if excluded:
            placeholders = ",".join("?" for _ in excluded)
            clauses.append(f"f.conversation_uid NOT IN ({placeholders})")
            args.extend(excluded)

        if min_captured_at is not None:
            clauses.append("s.captured_at >= ?")
            args.append(float(min_captured_at))

        if project_id:
            project_uids = [
                row["project_uid"]
                for row in self.conn.execute(
                    "SELECT project_uid FROM projects WHERE project_uid=? OR id=?",
                    (project_id, project_id),
                )
            ]
            if project_uids:
                clauses.append("c.project_uid IN (" + ",".join("?" for _ in project_uids) + ")")
                args.extend(project_uids)
            else:
                clauses.append("c.project_id=?")
                args.append(project_id)
        if provider:
            clauses.append("c.provider=?")
            args.append(provider)
        if account_id:
            clauses.append("c.account_id=?")
            args.append(account_id)

        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY score, COALESCE(s.source_updated_at,c.update_time,c.create_time) DESC LIMIT ?"
        args.append(limit)

        try:
            rows = list(self.conn.execute(sql, args))
        except sqlite3.OperationalError:
            if not q:
                rows = list(self.conn.execute(sql, args))
            else:
                safe_q = '"' + str(q).replace('"', '""') + '"'
                args[0] = safe_q
                rows = list(self.conn.execute(sql, args))

        results = []
        for row in rows:
            item = dict(row)
            item["evidence_id"] = f"{item['snapshot_id']}:{item['message_uid']}"
            item["excerpt"] = item.get("content", "")
            results.append(item)
        return results

    def search_detailed(
        self,
        q,
        limit=20,
        project_id=None,
        provider=None,
        account_id=None,
        exclude_conversation_uids=None,
        min_captured_at=None,
    ):
        return self.search_messages(
            q,
            limit=limit,
            project_id=project_id,
            provider=provider,
            account_id=account_id,
            exclude_conversation_uids=exclude_conversation_uids,
            min_captured_at=min_captured_at,
        )

    def search(self, q, limit=20):
        hits = self.search_messages(q, limit=limit)
        seen: set[str] = set()
        out = []
        for hit in hits:
            if hit["conversation_uid"] in seen:
                continue
            seen.add(hit["conversation_uid"])
            out.append(hit)
        return out

# ArchiveDB uses one SQLite connection per instance. Serialize public operations so concurrent
# MCP/worker requests cannot interleave transactions on the same connection.
def _install_archive_db_locks() -> None:
    def synchronized(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            with self._lock:
                return method(self, *args, **kwargs)
        return wrapper

    for name, method in list(vars(ArchiveDB).items()):
        if name == "__init__" or name.startswith("_") or not callable(method):
            continue
        setattr(ArchiveDB, name, synchronized(method))


_install_archive_db_locks()
