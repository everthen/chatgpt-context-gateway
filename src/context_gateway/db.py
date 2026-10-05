import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS projects(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT, updated_at TEXT,
 provider TEXT NOT NULL DEFAULT 'chatgpt', account_id TEXT NOT NULL DEFAULT 'default',
 source TEXT NOT NULL DEFAULT 'chatgpt', raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations(
 id TEXT PRIMARY KEY, project_id TEXT, project_name TEXT, title TEXT,
 create_time REAL, update_time REAL, raw_path TEXT NOT NULL, raw_hash TEXT NOT NULL,
 indexed_text TEXT NOT NULL, raw_json TEXT NOT NULL,
 provider TEXT NOT NULL DEFAULT 'chatgpt', account_id TEXT NOT NULL DEFAULT 'default',
 source TEXT NOT NULL DEFAULT 'chatgpt'
);
CREATE INDEX IF NOT EXISTS idx_conv_project ON conversations(project_id);
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts USING fts5(
 conversation_id UNINDEXED, title, project_name, content
);
"""

class ArchiveDB:
    def __init__(self, path: Path, check_same_thread: bool = False):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=check_same_thread)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        migrations = {
            "projects": {
                "provider": "TEXT NOT NULL DEFAULT 'chatgpt'",
                "account_id": "TEXT NOT NULL DEFAULT 'default'",
                "source": "TEXT NOT NULL DEFAULT 'chatgpt'",
            },
            "conversations": {
                "provider": "TEXT NOT NULL DEFAULT 'chatgpt'",
                "account_id": "TEXT NOT NULL DEFAULT 'default'",
                "source": "TEXT NOT NULL DEFAULT 'chatgpt'",
            },
        }
        for table, columns in migrations.items():
            existing = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns.items():
                if name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_provider_account ON conversations(provider, account_id)")
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    def upsert_project(self, p: dict[str, Any]):
        provider = p.get("provider", "chatgpt")
        self.conn.execute(
            """INSERT INTO projects
            (id,name,created_at,updated_at,provider,account_id,source,raw_json)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, created_at=excluded.created_at, updated_at=excluded.updated_at,
              provider=excluded.provider, account_id=excluded.account_id,
              source=excluded.source, raw_json=excluded.raw_json""",
            (
                p["id"], p.get("name") or "", p.get("created_at"), p.get("updated_at"),
                provider, p.get("account_id", "default"), p.get("source", provider),
                json.dumps(p, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def upsert_conversation(self, c: dict[str, Any]):
        provider = c.get("provider", "chatgpt")
        self.conn.execute(
            """INSERT INTO conversations
            (id,project_id,project_name,title,create_time,update_time,raw_path,raw_hash,
             indexed_text,raw_json,provider,account_id,source)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              project_id=excluded.project_id, project_name=excluded.project_name,
              title=excluded.title, create_time=excluded.create_time, update_time=excluded.update_time,
              raw_path=excluded.raw_path, raw_hash=excluded.raw_hash,
              indexed_text=excluded.indexed_text, raw_json=excluded.raw_json,
              provider=excluded.provider, account_id=excluded.account_id, source=excluded.source""",
            (
                c["id"], c.get("project_id"), c.get("project_name"), c.get("title") or "Untitled",
                c.get("create_time"), c.get("update_time"), c["raw_path"], c["raw_hash"],
                c.get("indexed_text", ""), c.get("raw_json", "{}"),
                provider, c.get("account_id", "default"), c.get("source", provider),
            ),
        )
        self.conn.execute("DELETE FROM conversation_fts WHERE conversation_id=?", (c["id"],))
        self.conn.execute(
            "INSERT INTO conversation_fts VALUES(?,?,?,?)",
            (c["id"], c.get("title") or "Untitled", c.get("project_name") or "", c.get("indexed_text", "")),
        )
        self.conn.commit()

    def projects(self):
        return [
            dict(r) for r in self.conn.execute(
                "SELECT id,name,created_at,updated_at,provider,account_id,source FROM projects ORDER BY name"
            )
        ]

    def conversations(self, project_id=None):
        q = """SELECT id,project_id,project_name,title,create_time,update_time,raw_path,
                      provider,account_id,source FROM conversations"""
        args = ()
        if project_id:
            q += " WHERE project_id=?"
            args = (project_id,)
        q += " ORDER BY COALESCE(update_time,create_time) DESC"
        return [dict(r) for r in self.conn.execute(q, args)]

    def get(self, cid):
        row = self.conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None

    def search(self, q, limit=20):
        return [
            {k: v for k, v in row.items() if k not in {"indexed_text", "raw_json"}}
            for row in self.search_detailed(q, limit)
        ]

    def search_detailed(self, q, limit=20, project_id=None):
        limit = max(1, min(int(limit), 50))
        if not q:
            if project_id:
                return [
                    dict(r) for r in self.conn.execute(
                        """SELECT c.* FROM conversations c
                           WHERE c.project_id=?
                           ORDER BY COALESCE(c.update_time,c.create_time) DESC LIMIT ?""",
                        (project_id, limit),
                    )
                ]
            return [
                dict(r) for r in self.conn.execute(
                    """SELECT c.* FROM conversations c
                       ORDER BY COALESCE(c.update_time,c.create_time) DESC LIMIT ?""",
                    (limit,),
                )
            ]

        sql = """SELECT c.*, bm25(conversation_fts) AS score
                 FROM conversation_fts f
                 JOIN conversations c ON c.id=f.conversation_id
                 WHERE conversation_fts MATCH ?"""
        args: list[Any] = [q]
        if project_id:
            sql += " AND c.project_id=?"
            args.append(project_id)
        sql += " ORDER BY score, COALESCE(c.update_time,c.create_time) DESC LIMIT ?"
        args.append(limit)
        try:
            return [dict(r) for r in self.conn.execute(sql, args)]
        except sqlite3.OperationalError:
            safe_q = '"' + str(q).replace('"', '""') + '"'
            args[0] = safe_q
            return [dict(r) for r in self.conn.execute(sql, args)]
