import json
import threading
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse
import pytest

from context_gateway.db import ArchiveDB
from context_gateway.server import create_server

@pytest.fixture
def test_server(tmp_path: Path):
    db_file = tmp_path / "server_test.sqlite3"
    db = ArchiveDB(db_file, check_same_thread=False)

    p1 = {"id": "proj-abc", "name": "API Testing", "created_at": "2024-01-01", "updated_at": "2024-01-02", "provider": "chatgpt", "account_id": "main", "source": "chatgpt"}
    db.upsert_project(p1)

    c1 = {
        "id": "conv-xyz",
        "project_id": "proj-abc",
        "project_name": "API Testing",
        "title": "FastAPI vs Flask",
        "create_time": 1700000000.0,
        "update_time": 1700000100.0,
        "raw_path": "/path/to/raw.json",
        "raw_hash": "hash123",
        "indexed_text": "user:\nWhat are the tradeoffs between FastAPI and Flask?\n\nassistant:\nFastAPI is async-first.",
        "raw_json": '{"id": "conv-xyz", "title": "FastAPI vs Flask"}',
        "provider": "chatgpt",
        "account_id": "main",
        "source": "chatgpt",
    }
    db.upsert_conversation(c1)

    server = create_server(host="127.0.0.1", port=0, db=db, raw_dir=tmp_path / "raw")
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.shutdown()
    server.server_close()
    db.close()

def _get_json(url: str):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert "application/json" in resp.headers.get("Content-Type")
        return json.loads(resp.read().decode("utf-8"))


def _post_json(url: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert "application/json" in resp.headers.get("Content-Type")
        return json.loads(resp.read().decode("utf-8"))

def test_server_health(test_server: str):
    data = _get_json(f"{test_server}/health")
    assert data["status"] == "ok"
    assert data["version"] == "0.3.0"

def test_server_projects(test_server: str):
    projects = _get_json(f"{test_server}/projects")
    assert isinstance(projects, list)
    assert len(projects) == 1
    assert projects[0]["id"] == "proj-abc"
    assert projects[0]["name"] == "API Testing"

def test_server_project_conversations(test_server: str):
    convs = _get_json(f"{test_server}/projects/proj-abc/conversations")
    assert isinstance(convs, list)
    assert len(convs) == 1
    assert convs[0]["id"] == "conv-xyz"
    assert convs[0]["title"] == "FastAPI vs Flask"

def test_server_get_conversation(test_server: str):
    conv = _get_json(f"{test_server}/conversations/conv-xyz")
    assert conv["id"] == "conv-xyz"
    assert conv["title"] == "FastAPI vs Flask"
    assert "FastAPI is async-first" in conv["indexed_text"]

def test_server_snapshot_history(test_server: str):
    snapshots = _get_json(f"{test_server}/conversations/conv-xyz/snapshots")
    assert len(snapshots) == 1
    snapshot_id = snapshots[0]["snapshot_id"]
    snapshot = _get_json(f"{test_server}/snapshots/{urllib.parse.quote(snapshot_id, safe=":")}")
    assert snapshot["snapshot_id"] == snapshot_id
    assert snapshot["message_count"] >= 1
    assert snapshot["raw_hash"] == "hash123"


def test_server_get_conversation_not_found(test_server: str):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/conversations/non-existent-id")
    assert exc_info.value.code == 404

def test_server_search(test_server: str):
    results = _get_json(f"{test_server}/search?q=tradeoffs")
    assert len(results) == 1
    assert results[0]["id"] == "conv-xyz"

def test_server_search_missing_q(test_server: str):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/search")
    assert exc_info.value.code == 400

def test_server_not_found_endpoint(test_server: str):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/unknown/endpoint")
    assert exc_info.value.code == 404


def test_server_project_context(test_server: str):
    data = _get_json(f"{test_server}/projects/proj-abc/context?topic=tradeoffs")
    assert data["project"]["id"] == "proj-abc"
    assert data["evidence"][0]["id"] == "conv-xyz"
    assert "untrusted evidence" in data["packet"]

def test_server_continuity(test_server: str):
    data = _get_json(f"{test_server}/continuity?q=tradeoffs&project=proj-abc")
    assert data["query"] == "tradeoffs"
    assert data["evidence"][0]["id"] == "conv-xyz"

def test_server_timeline(test_server: str):
    data = _get_json(f"{test_server}/projects/proj-abc/timeline?limit=1")
    assert len(data) == 1
    assert data[0]["provider"] == "chatgpt"

def test_server_compare(test_server: str):
    data = _get_json(f"{test_server}/compare?ids=conv-xyz,conv-xyz")
    assert data["count"] == 2

def test_server_bad_limit(test_server: str):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(f"{test_server}/search?q=tradeoffs&limit=0")
    assert exc_info.value.code == 400



def test_server_context_request(test_server: str):
    data = _post_json(
        f"{test_server}/context",
        {
            "consumer": "hermes",
            "session_id": "s-current",
            "query": "FastAPI tradeoffs",
            "scope": {"providers": ["chatgpt"], "accounts": ["main"], "project": "proj-abc"},
            "budget": {"max_messages": 5, "max_bytes": 50000},
        },
    )
    assert data["request"]["consumer"] == "hermes"
    assert data["evidence"][0]["id"] == "conv-xyz"
    assert data["retrieval"]["budget"]["max_messages"] == 5


def test_server_acquisition_ingest(test_server: str, tmp_path: Path):
    payload = {
        "id": "camo-live-1",
        "title": "Latest browser conversation",
        "create_time": 1700000200.0,
        "update_time": 1700000300.0,
        "mapping": {
            "n1": {
                "id": "n1",
                "parent": None,
                "children": ["n2"],
                "message": {
                    "id": "m1",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["latest browser evidence"]},
                    "create_time": 1700000200.0,
                },
            },
            "n2": {
                "id": "n2",
                "parent": "n1",
                "children": [],
                "message": {
                    "id": "m2",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["acknowledged"]},
                    "create_time": 1700000300.0,
                },
            },
        },
        "current_node": "n2",
    }
    data = _post_json(
        f"{test_server}/acquisition/ingest",
        {
            "provider": "chatgpt",
            "account_id": "main",
            "project_id": "proj-abc",
            "project_name": "API Testing",
            "acquisition_method": "camofox",
            "payload": payload,
        },
    )
    assert data["snapshot_id"]
    assert data["acquisition"]["method"] == "camofox"
    assert data["raw_path"].endswith("snapshot-001.json")
