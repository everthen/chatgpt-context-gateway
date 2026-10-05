import json, sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS projects(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT, updated_at TEXT, raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations(
 id TEXT PRIMARY KEY, project_id TEXT, project_name TEXT, title TEXT,
 create_time REAL, update_time REAL, raw_path TEXT NOT NULL, raw_hash TEXT NOT NULL,
 indexed_text TEXT NOT NULL, raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_project ON conversations(project_id);
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_fts USING fts5(
 conversation_id UNINDEXED, title, project_name, content
);
"""

class ArchiveDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_project(self, p: dict[str,Any]):
        self.conn.execute(
            "INSERT INTO projects VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,created_at=excluded.created_at,updated_at=excluded.updated_at,raw_json=excluded.raw_json",
            (p["id"],p.get("name") or "",p.get("created_at"),p.get("updated_at"),json.dumps(p,ensure_ascii=False))
        )
        self.conn.commit()

    def upsert_conversation(self, c: dict[str,Any]):
        self.conn.execute(
            """INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET project_id=excluded.project_id,project_name=excluded.project_name,
               title=excluded.title,create_time=excluded.create_time,update_time=excluded.update_time,
               raw_path=excluded.raw_path,raw_hash=excluded.raw_hash,indexed_text=excluded.indexed_text,raw_json=excluded.raw_json""",
            tuple(c[k] for k in ("id","project_id","project_name","title","create_time","update_time","raw_path","raw_hash","indexed_text","raw_json"))
        )
        self.conn.execute("DELETE FROM conversation_fts WHERE conversation_id=?",(c["id"],))
        self.conn.execute("INSERT INTO conversation_fts VALUES(?,?,?,?)",(c["id"],c["title"],c["project_name"],c["indexed_text"]))
        self.conn.commit()

    def projects(self):
        return [dict(r) for r in self.conn.execute("SELECT id,name,created_at,updated_at FROM projects ORDER BY name")]

    def conversations(self, project_id=None):
        q="SELECT id,project_id,project_name,title,create_time,update_time,raw_path FROM conversations"
        args=()
        if project_id:
            q+=" WHERE project_id=?"; args=(project_id,)
        q+=" ORDER BY COALESCE(update_time,create_time) DESC"
        return [dict(r) for r in self.conn.execute(q,args)]

    def get(self, cid):
        r=self.conn.execute("SELECT * FROM conversations WHERE id=?",(cid,)).fetchone()
        return dict(r) if r else None

    def search(self, q, limit=20):
        return [dict(r) for r in self.conn.execute(
            """SELECT c.id,c.project_name,c.title,c.update_time
               FROM conversation_fts f JOIN conversations c ON c.id=f.conversation_id
               WHERE conversation_fts MATCH ? ORDER BY bm25(conversation_fts) LIMIT ?""",(q,limit)
        )]
