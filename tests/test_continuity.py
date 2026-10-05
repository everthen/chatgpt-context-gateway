from pathlib import Path

from context_gateway.continuity import compare, continuity, project_context, timeline
from context_gateway.db import ArchiveDB


def _conversation(cid, title, project_id="p1", project_name="Project One", update=1700000100):
    return {
        "id": cid,
        "project_id": project_id,
        "project_name": project_name,
        "title": title,
        "create_time": update - 10,
        "update_time": update,
        "raw_path": f"/raw/{cid}.json",
        "raw_hash": f"hash-{cid}",
        "indexed_text": f"user:\nDiscussion about {title}\n\nassistant:\nDecision for {title}.",
        "raw_json": "{}",
        "provider": "chatgpt",
        "account_id": "main",
        "source": "chatgpt",
    }


def test_project_context_and_continuity(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    db.upsert_project({
        "id": "p1",
        "name": "Project One",
        "created_at": "a",
        "updated_at": "b",
        "provider": "chatgpt",
        "account_id": "main",
        "source": "chatgpt",
    })
    db.upsert_conversation(_conversation("c1", "Architecture decisions", update=1700000100))
    db.upsert_conversation(_conversation("c2", "Engineering loop", update=1700000200))

    ctx = project_context(db, "Project One", topic="Architecture")
    assert ctx["project"]["id"] == "p1"
    assert ctx["evidence"][0]["id"] == "c1"
    assert "untrusted evidence" in ctx["packet"]

    cont = continuity(db, "Engineering loop", project="p1")
    assert cont["evidence"][0]["id"] == "c2"

    rows = timeline(db, "p1", limit=1)
    assert len(rows) == 1
    assert rows[0]["id"] == "c2"


def test_compare_has_provenance(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    db.upsert_conversation(_conversation("a", "A"))
    db.upsert_conversation(_conversation("b", "B"))
    result = compare(db, ["a", "b"])
    assert result["count"] == 2
    assert result["conversations"][0]["provider"] == "chatgpt"
    assert result["conversations"][0]["account_id"] == "main"

def test_openai_export_smoke(tmp_path: Path):
    import json
    from context_gateway.openai_export import import_openai_export

    source = tmp_path / "conversations.json"
    source.write_text(json.dumps([{
        "id": "c-export-1",
        "title": "Imported",
        "create_time": 1,
        "update_time": 2,
        "mapping": {},
    }]), encoding="utf-8")
    db = ArchiveDB(tmp_path / "export.sqlite3")
    summary = import_openai_export(source, "secondary", db, tmp_path / "raw")
    assert sum(summary.values()) == 1
    row = db.get("c-export-1")
    assert row["provider"] == "openai"
    assert row["account_id"] == "secondary"
    assert "/openai/secondary/" in row["raw_path"]
