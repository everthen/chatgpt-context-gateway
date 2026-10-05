import tempfile
from pathlib import Path
from context_gateway.db import ArchiveDB

def test_db_init_and_tables(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    db = ArchiveDB(db_file)
    assert db_file.exists()
    assert db.projects() == []
    assert db.conversations() == []
    db.close()

def test_upsert_project(tmp_path: Path):
    db = ArchiveDB(tmp_path / "test.sqlite3")
    p1 = {
        "id": "proj-1",
        "name": "Project Alpha",
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
    }
    db.upsert_project(p1)
    projects = db.projects()
    assert len(projects) == 1
    assert projects[0]["id"] == "proj-1"
    assert projects[0]["name"] == "Project Alpha"

    # Update on conflict
    p1_updated = {
        "id": "proj-1",
        "name": "Project Alpha Renamed",
        "created_at": "2024-01-01",
        "updated_at": "2024-01-03",
    }
    db.upsert_project(p1_updated)
    projects = db.projects()
    assert len(projects) == 1
    assert projects[0]["name"] == "Project Alpha Renamed"
    db.close()

def test_upsert_conversation_and_search(tmp_path: Path):
    db = ArchiveDB(tmp_path / "test.sqlite3")
    c1 = {
        "id": "conv-1",
        "project_id": "proj-1",
        "project_name": "Alpha",
        "title": "Setup Docker Kubernetes",
        "create_time": 1700000000.0,
        "update_time": 1700000100.0,
        "raw_path": "/data/raw/Alpha/conv-1.json",
        "raw_hash": "hash123",
        "indexed_text": "user:\nBagaimana cara deploy container di cluster k8s?\n\nassistant:\nGunakan deployment manifest.",
        "raw_json": '{"id": "conv-1"}',
    }
    c2 = {
        "id": "conv-2",
        "project_id": "proj-2",
        "project_name": "Beta",
        "title": "Machine Learning Training",
        "create_time": 1700000200.0,
        "update_time": 1700000300.0,
        "raw_path": "/data/raw/Beta/conv-2.json",
        "raw_hash": "hash456",
        "indexed_text": "user:\nBagaimana cara tuning hyperparameter transformer?\n\nassistant:\nGunakan Optuna.",
        "raw_json": '{"id": "conv-2"}',
    }
    db.upsert_conversation(c1)
    db.upsert_conversation(c2)

    # List all
    all_convs = db.conversations()
    assert len(all_convs) == 2

    # Filter by project_id
    alpha_convs = db.conversations(project_id="proj-1")
    assert len(alpha_convs) == 1
    assert alpha_convs[0]["id"] == "conv-1"

    # Get single
    conv = db.get("conv-1")
    assert conv is not None
    assert conv["title"] == "Setup Docker Kubernetes"
    assert db.get("non-existent") is None

    # Full text search: content
    res = db.search("Kubernetes")
    assert len(res) == 1
    assert res[0]["id"] == "conv-1"

    res_ml = db.search("transformer")
    assert len(res_ml) == 1
    assert res_ml[0]["id"] == "conv-2"

    # Search with special characters / punctuation
    res_punct = db.search("k8s?")
    assert len(res_punct) == 1
    assert res_punct[0]["id"] == "conv-1"

    db.close()
