from pathlib import Path
import pytest
from context_gateway.cli import main
from context_gateway.db import ArchiveDB

def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "projects" in captured.out
    assert "sync" in captured.out
    assert "chats" in captured.out
    assert "get" in captured.out
    assert "search" in captured.out
    assert "serve" in captured.out

def test_cli_projects_and_chats_empty(tmp_path: Path, capsys):
    db_file = tmp_path / "test.sqlite3"
    code = main(["--db", str(db_file), "projects"])
    assert code == 0
    captured = capsys.readouterr()
    assert "No projects found." in captured.out

    code = main(["--db", str(db_file), "chats"])
    assert code == 0
    captured = capsys.readouterr()
    assert "No conversations found." in captured.out

def test_cli_populated_workflow(tmp_path: Path, capsys):
    db_file = tmp_path / "test.sqlite3"
    db = ArchiveDB(db_file)
    p = {"id": "proj-1", "name": "Agent Engineering", "created_at": "2024-01-01", "updated_at": "2024-01-02"}
    db.upsert_project(p)
    c = {
        "id": "conv-1",
        "project_id": "proj-1",
        "project_name": "Agent Engineering",
        "title": "Hermes Agent Design",
        "create_time": 1700000000.0,
        "update_time": 1700000100.0,
        "raw_path": "/data/raw/Agent_Engineering/conv-1.json",
        "raw_hash": "hash-abc",
        "indexed_text": "user:\nDesign an autonomous coding agent.\n\nassistant:\nUse clear boundaries and iterative verification.",
        "raw_json": '{"id": "conv-1", "title": "Hermes Agent Design"}',
    }
    db.upsert_conversation(c)
    db.close()

    # projects command
    code = main(["--db", str(db_file), "projects"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Agent Engineering" in captured.out
    assert "proj-1" in captured.out

    # chats command
    code = main(["--db", str(db_file), "chats", "--project", "Agent Engineering"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Hermes Agent Design" in captured.out
    assert "conv-1" in captured.out

    # get command
    code = main(["--db", str(db_file), "get", "--conversation-id", "conv-1"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Hermes Agent Design" in captured.out
    assert "Design an autonomous coding agent." in captured.out

    # get --full
    code = main(["--db", str(db_file), "get", "--conversation-id", "conv-1", "--full"])
    assert code == 0
    captured = capsys.readouterr()
    assert '"title": "Hermes Agent Design"' in captured.out

    # search command
    code = main(["--db", str(db_file), "search", "autonomous"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Hermes Agent Design" in captured.out

    # sync command without credentials fails cleanly with error code 1
    code = main(["--db", str(db_file), "--env-file", "/nonexistent.env", "sync", "--project", "Agent Engineering"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Authentication error" in captured.err or "Authentication error" in captured.out
