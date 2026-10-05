from pathlib import Path

import pytest

from context_gateway.acquisition import ingest_camofox_observation, ingest_conversation_payload
from context_gateway.camofox import BrowserTurn, CamofoxObservation
from context_gateway.contracts import (
    ContextBudget,
    ContextContractError,
    ContextRequest,
    ContextScope,
    ContextTarget,
    CurrentSessionContext,
    FreshnessPolicy,
)
from context_gateway.continuity import context_request
from context_gateway.db import ArchiveDB
from context_gateway.normalize import make_record


def _payload(cid: str, text: str, update: float = 1700000000):
    nodes = [
        {
            "id": f"node-{cid}-0",
            "parent": None,
            "children": [f"node-{cid}-1"],
            "message": {
                "id": f"msg-{cid}-0",
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [text]},
                "create_time": update,
            },
        },
        {
            "id": f"node-{cid}-1",
            "parent": f"node-{cid}-0",
            "children": [],
            "message": {
                "id": f"msg-{cid}-1",
                "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": [f"reply to {text}"]},
                "create_time": update + 1,
            },
        },
    ]
    return {
        "id": cid,
        "title": f"Conversation {cid}",
        "create_time": update,
        "update_time": update,
        "mapping": {item["id"]: item for item in nodes},
        "current_node": nodes[-1]["id"],
    }


def _record(tmp_path: Path, cid: str, text: str, update: float = 1700000000):
    return make_record(
        _payload(cid, text, update),
        project_id="project-1",
        project_name="Engineering",
        raw_path=str(tmp_path / cid / "snapshot-001.json"),
        provider="chatgpt",
        account_id="main",
        source="export",
        captured_at=update,
    )


def test_context_request_contract_round_trip():
    request = ContextRequest.from_dict(
        {
            "consumer": "hermes",
            "session_id": "session-current",
            "query": "continue engineering loop",
            "scope": {
                "providers": ["openai", "google"],
                "accounts": ["main"],
                "project": "Engineering",
            },
            "freshness": {
                "max_age_seconds": 86400,
                "allow_live_acquisition": True,
                "require_fresh": True,
            },
            "budget": {"max_messages": 12, "max_bytes": 50000},
            "trust": "historical_evidence",
            "exclude_conversation_uids": ["current-uid"],
        }
    )
    encoded = request.to_dict()
    restored = ContextRequest.from_dict(encoded)
    assert restored == request
    assert restored.scope.providers == ("openai", "google")
    assert restored.scope.accounts == ("main",)
    assert restored.budget.max_messages == 12


@pytest.mark.parametrize(
    "value",
    [
        {"max_messages": 0, "max_bytes": 50000},
        {"max_messages": 10, "max_bytes": 100},
    ],
)
def test_invalid_budget_is_rejected(value):
    with pytest.raises(ContextContractError):
        ContextBudget.from_dict(value)


def test_ingestion_creates_snapshot_and_checkpoint(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    result = ingest_conversation_payload(
        _payload("camo-c1", "latest from browser"),
        project_id="project-1",
        project_name="Engineering",
        provider="chatgpt",
        account_id="main",
        acquisition_method="camofox",
        db=db,
        raw_dir=tmp_path / "raw",
    )
    assert result["snapshot_id"]
    assert result["raw_path"].endswith("snapshot-001.json")
    checkpoint = db.get_acquisition_checkpoint(
        "chatgpt", "main", "conversation", "camo-c1", "camofox"
    )
    assert checkpoint["status"] == "success"
    assert checkpoint["method"] == "camofox"
    assert checkpoint["last_success_at"] is not None


def test_incomplete_camofox_observation_is_not_promoted(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    observation = CamofoxObservation(
        provider="chatgpt",
        account_id="main",
        conversation_id="camo-1",
        title="Engineering",
        url="https://chatgpt.com/c/camo-1",
        turns=(BrowserTurn("user", "partial", 0),),
        snapshot_hashes=("h1",),
        raw_snapshots=("partial snapshot",),
        scroll_rounds=3,
        complete=False,
        captured_at=1700000000,
    )

    with pytest.raises(ValueError, match="incomplete"):
        ingest_camofox_observation(
            observation,
            project_id="project-1",
            project_name="Engineering",
            db=db,
            raw_dir=tmp_path / "raw",
        )


def test_context_request_excludes_current_session_evidence(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    row_current = _record(tmp_path, "current-conversation", "engineering loop latest decision")
    row_old = _record(tmp_path, "historical-conversation", "engineering loop latest decision")
    db.upsert_conversation(row_current)
    db.upsert_conversation(row_old)

    current_uid = db._conversation_uid_from_record(row_current)
    result = context_request(
        db,
        ContextRequest(
            consumer="chatgpt",
            session_id="current-session",
            query="engineering loop latest decision",
            exclude_conversation_uids=(current_uid,),
            budget=ContextBudget(max_messages=10, max_bytes=50000),
        ),
    )

    old_uid = db._conversation_uid_from_record(row_old)
    ids = {item["conversation_uid"] for item in result["evidence"]}
    assert current_uid not in ids
    assert old_uid in ids
    assert result["retrieval"]["excluded_conversation_uids"] == [current_uid]


def test_context_request_enforces_freshness_and_exposes_acquisition_needed(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    stale = _record(tmp_path, "stale", "freshness test evidence", update=1700000000)
    db.upsert_conversation(stale)

    result = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="s1",
            query="freshness test evidence",
            freshness=FreshnessPolicy(
                max_age_seconds=60,
                allow_live_acquisition=True,
                require_fresh=True,
            ),
        ),
    )

    assert result["evidence"] == []
    assert result["acquisition"]["status"] == "acquisition_required"
    assert result["acquisition"]["next_action"] == "run_provider_acquisition"
    assert result["retrieval"]["freshness"]["fresh_evidence_count"] == 0


def test_context_request_can_union_multiple_provider_scopes(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    db.upsert_project(
        {
            "id": "p-openai",
            "name": "Engineering",
            "provider": "openai",
            "account_id": "main",
        }
    )
    db.upsert_project(
        {
            "id": "p-google",
            "name": "Engineering",
            "provider": "google",
            "account_id": "main",
        }
    )

    openai = _record(tmp_path, "openai-1", "broker bootstrap engineering loop")
    openai["provider"] = "openai"
    openai["account_id"] = "main"
    openai["project_id"] = "p-openai"
    google = _record(tmp_path, "google-1", "broker bootstrap engineering loop")
    google["provider"] = "google"
    google["account_id"] = "main"
    google["project_id"] = "p-google"
    db.upsert_conversation(openai)
    db.upsert_conversation(google)

    result = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="s2",
            query="broker bootstrap engineering loop",
            scope=ContextScope(
                providers=("openai", "google"),
                accounts=("main",),
                project="Engineering",
            ),
        ),
    )
    assert {item["provider"] for item in result["evidence"]} == {"openai", "google"}
    assert result["request"]["consumer"] == "hermes"



def test_context_request_continuation_uses_current_session_antecedent(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    row = _record(
        tmp_path,
        "continuation-conversation",
        "activate the engine as Hermes default and run the golden test",
        update=1700000000,
    )
    db.upsert_conversation(row)

    result = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="s-cont",
            query="Gas bro! Thinking",
            current_session=__import__("context_gateway.contracts", fromlist=["CurrentSessionContext"]).CurrentSessionContext(
                session_id="s-cont",
                current_conversation_uid=db._conversation_uid_from_record(row),
                current_conversation_id="continuation-conversation",
                last_assistant_commitment="activate the engine as Hermes default and run the golden test",
                continuation_requested=True,
            ),
            freshness=FreshnessPolicy(max_age_seconds=None),
        ),
    )

    assert result["continuation"]["detected"] is True
    assert result["continuation"]["last_assistant_commitment"]
    assert result["evidence"]
    assert any("activate the engine as Hermes default" in item["excerpt"] for item in result["evidence"])


def test_context_request_requires_fresh_current_evidence(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    old = _record(
        tmp_path,
        "current-conversation",
        "activate engine and run golden test",
        update=1700000000,
    )
    db.upsert_conversation(old)
    current_uid = db._conversation_uid_from_record(old)

    result = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="s-fresh",
            query="Gas bro! Thinking",
            current_session=__import__("context_gateway.contracts", fromlist=["CurrentSessionContext"]).CurrentSessionContext(
                session_id="s-fresh",
                current_conversation_uid=current_uid,
                current_conversation_id="current-conversation",
                last_assistant_commitment="activate engine and run golden test",
                continuation_requested=True,
            ),
            freshness=FreshnessPolicy(
                mode="require_fresh",
                max_observation_age_seconds=60,
                allow_live_acquisition=True,
            ),
        ),
    )

    assert result["evidence"] == []
    assert result["acquisition"]["status"] == "acquisition_required"
    assert result["continuation"]["status"] == "awaiting_acquisition"


def test_run_context_request_acquires_and_retries(tmp_path: Path):
    from context_gateway.acquisition import run_context_request

    db = ArchiveDB(tmp_path / "db.sqlite3")
    old = _record(
        tmp_path,
        "acquire-me",
        "activate engine and run golden test",
        update=1700000000,
    )
    db.upsert_conversation(old)

    calls = []

    def adapter(request, database):
        calls.append(request.session_id)
        fresh = _payload(
            "acquire-me",
            "activate engine and run golden test now",
            update=__import__("time").time(),
        )
        ingest_conversation_payload(
            fresh,
            project_id="project-1",
            project_name="Engineering",
            provider="chatgpt",
            account_id="main",
            acquisition_method="fake-acquisition",
            db=database,
            raw_dir=tmp_path / "raw",
        )
        return {"method": "fake-acquisition"}

    request = ContextRequest(
        consumer="hermes",
        session_id="s-acquire",
        query="activate engine and run golden test",
        current_session=__import__("context_gateway.contracts", fromlist=["CurrentSessionContext"]).CurrentSessionContext(
            session_id="s-acquire",
            current_conversation_uid=db._conversation_uid_from_record(old),
            current_conversation_id="acquire-me",
            continuation_requested=True,
        ),
        freshness=FreshnessPolicy(
            mode="require_fresh",
            max_observation_age_seconds=60,
            allow_live_acquisition=True,
        ),
    )

    result = run_context_request(db, request, adapter=adapter, max_attempts=1)

    assert calls == ["s-acquire"]
    assert result["acquisition"]["status"] == "acquired_and_retried"
    assert result["evidence"]
    assert any(item["snapshot_seq"] >= 2 for item in result["evidence"])


def test_targeted_session_retrieval_is_exact_and_ordered(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    rows = [
        _record(tmp_path, "session-a", "A_ONLY context"),
        _record(tmp_path, "session-b", "B_ONLY context"),
        _record(tmp_path, "session-c", "C_ONLY context"),
    ]
    for row in rows:
        db.upsert_conversation(row)

    a_uid = db._conversation_uid_from_record(rows[0])
    result = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="consumer-1",
            query="",
            intent="retrieve",
            target=ContextTarget(type="conversation", conversation_uid=a_uid),
            budget=ContextBudget(max_messages=10, max_bytes=50000),
        ),
    )

    assert result["retrieval"]["method"] == "exact-snapshot"
    assert result["target"]["resolved_snapshot_id"]
    assert result["retrieval"]["read_fence"] == result["target"]["resolved_snapshot_id"]
    assert [item["role"] for item in result["transcript"]] == ["user", "assistant"]
    assert "A_ONLY" in result["transcript"][0]["text"]
    assert all("B_ONLY" not in item["text"] for item in result["transcript"])
    assert all("C_ONLY" not in item["text"] for item in result["transcript"])
    assert result["completeness"]["status"] == "complete"


def test_targeted_snapshot_read_fence_is_pinned(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    first = _record(tmp_path, "fenced", "first snapshot")
    db.upsert_conversation(first)
    uid = db._conversation_uid_from_record(first)
    first_snapshot = db.current_snapshot(uid)["snapshot_id"]

    second = _record(tmp_path, "fenced", "second snapshot", update=1700000010)
    db.upsert_conversation(second)

    assert db.current_snapshot(uid)["snapshot_id"] != first_snapshot
    result = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="fence",
            query="",
            intent="retrieve",
            target=ContextTarget(
                type="conversation",
                conversation_uid=uid,
                snapshot="explicit",
                snapshot_id=first_snapshot,
            ),
        ),
    )

    assert result["target"]["resolved_snapshot_id"] == first_snapshot
    assert result["retrieval"]["read_fence"] == first_snapshot
    assert result["transcript"][0]["text"] == "first snapshot"


def test_targeted_transcript_budget_returns_cursor(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    row = _record(tmp_path, "paged", "page one")
    db.upsert_conversation(row)
    uid = db._conversation_uid_from_record(row)
    snapshot_id = db.current_snapshot(uid)["snapshot_id"]

    first = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="page-1",
            query="",
            intent="retrieve",
            target=ContextTarget(type="conversation", conversation_uid=uid),
            budget=ContextBudget(max_messages=1, max_bytes=50000),
        ),
    )

    assert first["completeness"]["status"] == "partial"
    assert first["next_cursor"].startswith(snapshot_id + "|")

    second = context_request(
        db,
        ContextRequest(
            consumer="hermes",
            session_id="page-2",
            query="",
            intent="retrieve",
            target=ContextTarget(
                type="conversation",
                conversation_uid=uid,
                snapshot="explicit",
                snapshot_id=snapshot_id,
                cursor=first["next_cursor"],
            ),
            budget=ContextBudget(max_messages=10, max_bytes=50000),
        ),
    )
    assert second["target"]["resolved_snapshot_id"] == snapshot_id
    assert second["transcript"][0]["ordinal"] == 1
    assert second["completeness"]["status"] == "complete"


def test_reobservation_refreshes_current_observation_time(tmp_path: Path):
    import time

    db = ArchiveDB(tmp_path / "db.sqlite3")
    row = _record(tmp_path, "same-content", "same content")
    db.upsert_conversation(row)
    uid = db._conversation_uid_from_record(row)
    before = db.current_snapshot(uid)["last_observed_at"]

    time.sleep(0.01)
    refreshed = dict(row)
    refreshed["captured_at"] = time.time()
    db.upsert_conversation(refreshed)
    after = db.current_snapshot(uid)["last_observed_at"]

    assert db.snapshots(uid)
    assert db.current_snapshot(uid)["snapshot_id"].endswith("snapshot-000001")
    assert after > before


def test_camofox_preserves_duplicate_message_occurrences():
    from context_gateway.camofox import collect_conversation

    class FakeClient:
        def get_tab(self, user_id, tab_id):
            return {
                "tabId": tab_id,
                "url": "https://chatgpt.com/c/duplicate-test",
                "title": "Duplicate test",
            }

        def snapshot(self, user_id, tab_id):
            return {
                "snapshot": """- heading "You said:"
- paragraph: "same"
- heading "ChatGPT said:"
- paragraph: "reply"
- heading "You said:"
- paragraph: "same"
- heading "ChatGPT said:"
- paragraph: "reply 2"
"""
            }

        def scroll_metrics(self, user_id, tab_id):
            return {"scrollTop": 0, "scrollHeight": 1000, "clientHeight": 500}

    observation = collect_conversation(
        FakeClient(),
        user_id="camofox-human-login",
        tab_id="tab-1",
        account_id="main",
        settle_seconds=0,
    )

    assert observation.complete is True
    assert [(turn.role, turn.text) for turn in observation.turns] == [
        ("user", "\"same\""),
        ("assistant", "\"reply\""),
        ("user", "\"same\""),
        ("assistant", "\"reply 2\""),
    ]
