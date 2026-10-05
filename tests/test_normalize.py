import json
from context_gateway.normalize import extract_messages, extract_text, make_record, stable_hash

def test_stable_hash_deterministic():
    obj1 = {"b": 2, "a": 1, "c": [3, 4]}
    obj2 = {"a": 1, "c": [3, 4], "b": 2}
    assert stable_hash(obj1) == stable_hash(obj2)
    assert len(stable_hash(obj1)) == 64

def test_stable_hash_different():
    obj1 = {"a": 1}
    obj2 = {"a": 2}
    assert stable_hash(obj1) != stable_hash(obj2)

def test_extract_text_empty():
    assert extract_text({}) == ""
    assert extract_text({"mapping": {}}) == ""

def test_extract_messages_are_canonical_and_ordered():
    conv = {
        "current_node": "node-2",
        "mapping": {
            "node-1": {
                "id": "node-1",
                "parent": None,
                "children": ["node-2"],
                "message": {
                    "id": "msg-1",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["First"]},
                },
            },
            "node-2": {
                "id": "node-2",
                "parent": "node-1",
                "children": [],
                "message": {
                    "id": "msg-2",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Second"]},
                },
            },
        },
    }
    messages = extract_messages(conv)
    assert [m["provider_message_id"] for m in messages] == ["msg-1", "msg-2"]
    assert [m["ordinal"] for m in messages] == [0, 1]
    assert messages[1]["parent_message_id"] == "msg-1"


def test_extract_text_linear():
    conv = {
        "current_node": "node-3",
        "mapping": {
            "node-1": {
                "id": "node-1",
                "parent": None,
                "children": ["node-2"],
                "message": None,
            },
            "node-2": {
                "id": "node-2",
                "parent": "node-1",
                "children": ["node-3"],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Halo ChatGPT"]},
                },
            },
            "node-3": {
                "id": "node-3",
                "parent": "node-2",
                "children": [],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Halo! Ada yang bisa dibantu?"]},
                },
            },
        },
    }
    extracted = extract_text(conv)
    assert "user:\nHalo ChatGPT" in extracted
    assert "assistant:\nHalo! Ada yang bisa dibantu?" in extracted

def test_extract_text_branching_fallback():
    # If current_node is missing, it picks the last leaf node
    conv = {
        "mapping": {
            "root": {
                "id": "root",
                "parent": None,
                "children": ["c1"],
                "message": None,
            },
            "c1": {
                "id": "c1",
                "parent": "root",
                "children": [],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Leaf branch message"]},
                },
            },
        }
    }
    extracted = extract_text(conv)
    assert "user:\nLeaf branch message" in extracted

def test_extract_text_filter_thoughts_and_roles():
    conv = {
        "current_node": "node-3",
        "mapping": {
            "node-1": {
                "id": "node-1",
                "parent": None,
                "children": ["node-2"],
                "message": {
                    "author": {"role": "system"},  # Should be ignored (only user/assistant/tool)
                    "content": {"content_type": "text", "parts": ["System prompt"]},
                },
            },
            "node-2": {
                "id": "node-2",
                "parent": "node-1",
                "children": ["node-3"],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "thoughts", "parts": ["Hidden reasoning"]},  # Should be ignored
                },
            },
            "node-3": {
                "id": "node-3",
                "parent": "node-2",
                "children": [],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Visible reply"]},
                },
            },
        },
    }
    extracted = extract_text(conv)
    assert "System prompt" not in extracted
    assert "Hidden reasoning" not in extracted
    assert "assistant:\nVisible reply" in extracted

def test_make_record():
    payload = {
        "id": "conv-123",
        "title": "Percakapan Arsitektur",
        "create_time": 1700000000.0,
        "update_time": 1700001000.0,
        "mapping": {
            "n1": {
                "id": "n1",
                "parent": None,
                "children": [],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Jelaskan REST API"]},
                },
            }
        },
        "current_node": "n1",
    }
    rec = make_record(
        payload,
        project_id="proj-456",
        project_name="Arsitektur Backend",
        raw_path="/path/to/raw.json",
    )
    assert rec["id"] == "conv-123"
    assert rec["project_id"] == "proj-456"
    assert rec["project_name"] == "Arsitektur Backend"
    assert rec["title"] == "Percakapan Arsitektur"
    assert rec["create_time"] == 1700000000.0
    assert rec["update_time"] == 1700001000.0
    assert rec["raw_path"] == "/path/to/raw.json"
    assert "user:\nJelaskan REST API" in rec["indexed_text"]
    assert rec["raw_hash"] == stable_hash(payload)
    assert json.loads(rec["raw_json"])["title"] == "Percakapan Arsitektur"
