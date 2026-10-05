import json
from pathlib import Path

from context_gateway.continuity import continuity
from context_gateway.db import ArchiveDB
from context_gateway.normalize import make_record


def _record(
    cid: str,
    text: str,
    *,
    provider: str = "chatgpt",
    account_id: str = "main",
    project_id: str = "project-1",
    project_name: str = "Jambu Research",
    update: float = 1700000000,
):
    parts = []
    for index, (role, message) in enumerate(
        [("user", text), ("assistant", f"Evidence about {text}")]
    ):
        parts.append(
            {
                "id": f"node-{cid}-{index}",
                "parent": parts[-1]["id"] if parts else None,
                "children": [],
                "message": {
                    "id": f"msg-{cid}-{index}",
                    "author": {"role": role},
                    "content": {"content_type": "text", "parts": [message]},
                    "create_time": update + index,
                },
            }
        )
    payload = {
        "id": cid,
        "title": f"{provider} {cid}",
        "create_time": update,
        "update_time": update,
        "mapping": {item["id"]: item for item in parts},
        "current_node": parts[-1]["id"],
    }
    return make_record(
        payload,
        project_id=project_id,
        project_name=project_name,
        raw_path=f"/raw/{provider}/{account_id}/{cid}/snapshot-001.json",
        provider=provider,
        account_id=account_id,
        source=provider,
        captured_at=update,
    )


def test_snapshot_history_is_append_only_and_deduplicated(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    raw_dir = tmp_path / "raw"

    first = _record("c1", "alpha mango")
    first["raw_path"] = str(raw_dir / "chatgpt" / "main" / "Jambu_Research" / "c1" / "snapshot-001.json")
    Path(first["raw_path"]).parent.mkdir(parents=True)
    Path(first["raw_path"]).write_text(json.dumps({"id": "c1", "version": 1}), encoding="utf-8")
    db.upsert_conversation(first)

    same = dict(first)
    same["captured_at"] = 1700000100
    db.upsert_conversation(same)

    changed = _record("c1", "alpha mango changed", update=1700000200)
    changed["raw_path"] = str(raw_dir / "chatgpt" / "main" / "Jambu_Research" / "c1" / "snapshot-002.json")
    Path(changed["raw_path"]).write_text(json.dumps({"id": "c1", "version": 2}), encoding="utf-8")
    db.upsert_conversation(changed)

    snapshots = db.snapshots("c1")
    assert [s["snapshot_seq"] for s in snapshots] == [1, 2]
    assert snapshots[0]["raw_hash"] != snapshots[1]["raw_hash"]
    current = db.get("c1")["current_snapshot"]
    assert current["snapshot_id"] == snapshots[1]["snapshot_id"]
    old_snapshot = db.get_snapshot(snapshots[0]["snapshot_id"])
    new_snapshot = db.get_snapshot(snapshots[1]["snapshot_id"])
    assert old_snapshot["messages"][0]["text"] == "alpha mango"
    assert new_snapshot["messages"][0]["text"] == "alpha mango changed"


def test_same_conversation_id_isolated_by_provider_and_account(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")

    rows = [
        _record("same-id", "chatgpt evidence", provider="openai", account_id="main"),
        _record("same-id", "secondary evidence", provider="openai", account_id="secondary"),
        _record("same-id", "gemini evidence", provider="google", account_id="main"),
    ]
    for row in rows:
        db.upsert_conversation(row)

    conversations = db.conversations()
    assert len(conversations) == 3
    assert len({row["conversation_uid"] for row in conversations}) == 3

    db.upsert_project({"id": "same-project", "name": "Shared", "provider": "openai", "account_id": "main"})
    db.upsert_project({"id": "same-project", "name": "Shared", "provider": "google", "account_id": "main"})
    try:
        continuity(db, "evidence", project="Shared")
        assert False, "project name must be ambiguous across scopes"
    except ValueError as exc:
        assert "ambiguous" in str(exc)

    try:
        db.get("same-id")
        assert False, "raw conversation id must be ambiguous across scopes"
    except ValueError as exc:
        assert "ambiguous" in str(exc)


def test_message_level_search_returns_exact_snapshot_provenance(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    row = _record("c42", "provenance boundary")
    db.upsert_conversation(row)

    hits = db.search_messages("provenance boundary")
    assert hits
    hit = next(item for item in hits if item["role"] == "user")
    assert hit["id"] == "c42"
    assert hit["message_id"] == "msg-c42-0"
    assert hit["provider"] == "chatgpt"
    assert hit["account_id"] == "main"
    assert hit["snapshot_id"].startswith(hit["conversation_uid"] + ":snapshot-")
    assert hit["raw_hash"]
    assert hit["raw_path"].endswith("snapshot-001.json")
    assert hit["excerpt"] == "provenance boundary"


def test_universal_continuity_can_combine_provider_evidence(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    db.upsert_project({
        "id": "project-1",
        "name": "Jambu Research",
        "provider": "openai",
        "account_id": "main",
        "source": "chatgpt",
    })

    db.upsert_conversation(_record("chat-a", "jambu nutrition", provider="openai", account_id="main"))
    db.upsert_conversation(_record("chat-b", "jambu botanical research", provider="google", account_id="main"))
    db.upsert_conversation(_record("chat-c", "jambu cultivation comparison", provider="perplexity", account_id="main"))

    result = continuity(db, "jambu")
    assert result["retrieval"]["granularity"] == "message"
    assert result["schema_version"] == "context-bundle.v1"
    assert {item["provider"] for item in result["evidence"]} == {"openai", "google", "perplexity"}
    assert all(item["snapshot_id"] for item in result["provenance"])
    assert all(item["message_id"] for item in result["provenance"])
    assert result["conflict_analysis"]["status"] == "not_inferred"
    assert "EXACT EVIDENCE:" in result["packet"]

    scoped = continuity(db, "jambu", provider="google", account_id="main")
    assert {item["provider"] for item in scoped["evidence"]} == {"google"}
    assert scoped["scope"]["provider"] == "google"
    assert scoped["scope"]["account_id"] == "main"
