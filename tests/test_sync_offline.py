import json
from pathlib import Path
from unittest.mock import MagicMock

from context_gateway.client import ChatGPTClient
from context_gateway.db import ArchiveDB
from context_gateway.sync import sync_project, sync_projects

def test_sync_project_offline(tmp_path: Path):
    db_file = tmp_path / "archive.sqlite3"
    raw_dir = tmp_path / "raw"
    db = ArchiveDB(db_file)

    mock_client = MagicMock(spec=ChatGPTClient)
    mock_client.list_projects.return_value = [
        {"id": "proj-101", "name": "Deep Learning / AI", "created_at": "2024-01-01", "updated_at": "2024-01-02"}
    ]
    mock_client.list_conversations.return_value = {
        "items": [
            {"id": "conv-a", "title": "PyTorch Optimization"},
        ],
        "total": 1,
    }
    mock_client.get_conversation.return_value = {
        "id": "conv-a",
        "title": "PyTorch Optimization",
        "create_time": 1700000000.0,
        "update_time": 1700000500.0,
        "mapping": {
            "node-1": {
                "id": "node-1",
                "parent": None,
                "children": [],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["How to profile CUDA memory?"]},
                },
            }
        },
        "current_node": "node-1",
    }

    records = sync_project(
        project_name="Deep Learning / AI",
        client=mock_client,
        db=db,
        raw_dir=raw_dir,
    )

    assert len(records) == 1
    assert records[0]["id"] == "conv-a"
    assert records[0]["project_name"] == "Deep Learning / AI"

    # Check safe folder name in data/raw
    # "Deep Learning / AI" -> safe project name e.g. "Deep_Learning_AI"
    safe_folder = "Deep_Learning_AI"
    raw_file = raw_dir / "chatgpt" / "default" / safe_folder / "conv-a" / "snapshot-001.json"
    assert raw_file.exists()

    payload_on_disk = json.loads(raw_file.read_text(encoding="utf-8"))
    assert payload_on_disk["id"] == "conv-a"
    assert payload_on_disk["title"] == "PyTorch Optimization"

    # Check DB
    db_conv = db.get("conv-a")
    assert db_conv is not None
    assert db_conv["title"] == "PyTorch Optimization"
    assert "How to profile CUDA memory?" in db_conv["indexed_text"]

    # Check search
    search_res = db.search("CUDA")
    assert len(search_res) == 1
    assert search_res[0]["id"] == "conv-a"

    # A second sync with the same payload must not create a duplicate snapshot.
    records_again = sync_project(
        project_name="Deep Learning / AI",
        client=mock_client,
        db=db,
        raw_dir=raw_dir,
    )
    assert records_again[0]["snapshot_id"] == records[0]["snapshot_id"]
    assert len(db.snapshots("conv-a")) == 1

    # A changed remote payload creates a new immutable snapshot and advances current.
    changed_payload = dict(mock_client.get_conversation.return_value)
    changed_payload["update_time"] = 1700000600.0
    changed_payload["mapping"] = {
        "node-1": {
            "id": "node-1",
            "parent": None,
            "children": ["node-2"],
            "message": {
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": ["How to profile CUDA memory?"]},
            },
        },
        "node-2": {
            "id": "node-2",
            "parent": "node-1",
            "children": [],
            "message": {
                "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": ["Measure allocations with profiler."]},
            },
        },
    }
    mock_client.get_conversation.return_value = changed_payload
    changed = sync_project(
        project_name="Deep Learning / AI",
        client=mock_client,
        db=db,
        raw_dir=raw_dir,
    )
    assert len(db.snapshots("conv-a")) == 2
    assert changed[0]["snapshot_id"] != records[0]["snapshot_id"]
    assert changed[0]["snapshot_id"].endswith("snapshot-000002")

    db.close()


def test_sync_projects_offline(tmp_path: Path):
    db_file = tmp_path / "archive.sqlite3"
    raw_dir = tmp_path / "raw"
    db = ArchiveDB(db_file)

    mock_client = MagicMock(spec=ChatGPTClient)
    mock_client.list_projects.return_value = [
        {"id": "p1", "name": "Project One"},
        {"id": "p2", "name": "Project Two"},
    ]
    mock_client.list_conversations.side_effect = [
        {"items": [{"id": "c1", "title": "Conv 1"}], "total": 1},
        {"items": [{"id": "c2", "title": "Conv 2"}], "total": 1},
    ]
    mock_client.get_conversation.side_effect = [
        {
            "id": "c1",
            "title": "Conv 1",
            "mapping": {
                "n1": {
                    "id": "n1",
                    "parent": None,
                    "children": [],
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Message in P1"]},
                    },
                }
            },
            "current_node": "n1",
        },
        {
            "id": "c2",
            "title": "Conv 2",
            "mapping": {
                "n2": {
                    "id": "n2",
                    "parent": None,
                    "children": [],
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Message in P2"]},
                    },
                }
            },
            "current_node": "n2",
        },
    ]

    summary = sync_projects(client=mock_client, db=db, raw_dir=raw_dir)
    assert summary == {"Project One": 1, "Project Two": 1}

    assert (raw_dir / "chatgpt" / "default" / "Project_One" / "c1" / "snapshot-001.json").exists()
    assert (raw_dir / "chatgpt" / "default" / "Project_Two" / "c2" / "snapshot-001.json").exists()

    assert len(db.conversations()) == 2
    db.close()
