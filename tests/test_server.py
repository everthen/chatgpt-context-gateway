import json
import threading
from pathlib import Path
import urllib.request
import urllib.error
import pytest

from context_gateway.db import ArchiveDB
from context_gateway.server import create_server

@pytest.fixture
def test_server(tmp_path: Path):
    db_file = tmp_path / "server_test.sqlite3"
    db = ArchiveDB(db_file, check_same_thread=False)

    p1 = {"id": "proj-abc", "name": "API Testing", "created_at": "2024-01-01", "updated_at": "2024-01-02"}
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
    }
    db.upsert_conversation(c1)

    server = create_server(host="127.0.0.1", port=0, db=db)
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

def test_server_health(test_server: str):
    data = _get_json(f"{test_server}/health")
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"

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
