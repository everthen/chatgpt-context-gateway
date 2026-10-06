import pytest

mcp = pytest.importorskip("mcp")

from context_gateway.mcp_server import _host_identity_probe, _safe_handoff, build_mcp


def test_host_identity_probe_hashes_openai_session_without_exposing_it():
    result = _host_identity_probe(
        {"openai/session": "session-secret", "custom/example": "value"},
        "request-1",
    )

    assert result["request_id"] == "request-1"
    assert result["meta_keys"] == ["custom/example", "openai/session"]
    assert result["openai_session"]["present"] is True
    assert result["openai_session"]["length"] == len("session-secret")
    assert result["openai_session"]["fingerprint"]
    assert "session-secret" not in str(result)
    assert result["raw_identity_returned"] is False


def test_host_identity_probe_accepts_mcp_pydantic_meta():
    from mcp.types import CallToolRequestParams

    request = CallToolRequestParams.model_validate(
        {"name": "context_host_identity_probe", "_meta": {"openai/session": "session-secret"}}
    )
    result = _host_identity_probe(request.meta, "request-1")

    assert result["openai_session"]["present"] is True
    assert result["openai_session"]["fingerprint"]
    assert result["raw_identity_returned"] is False


def test_host_identity_probe_absent_session():
    result = _host_identity_probe({"openai/locale": "id-ID"}, "request-2")

    assert result["openai_session"] == {
        "present": False,
        "fingerprint": None,
        "length": None,
    }
    assert result["raw_identity_returned"] is False


def test_mcp_tool_registry(tmp_path):
    server = build_mcp(tmp_path / "mcp.sqlite3")
    names = [tool.name for tool in server._tool_manager.list_tools()]
    assert names == [
        "context_request",
        "context_host_identity_probe",
        "context_host_session_bind",
        "context_host_session_resolve",
        "context_capture_hot",
        "context_account_login",
        "context_account_status",
        "context_handoff_prepare",
        "context_handoff_redeem",
        "context_search",
        "context_get_conversation",
        "context_get_snapshot",
        "context_project_context",
        "context_timeline",
        "context_continuity",
        "context_compare",
    ]


def test_safe_handoff_never_returns_bearer_capability():
    result = _safe_handoff({
        "handoff_id": "secret-bearer",
        "provider": "chatgpt",
        "account_id": "main",
        "conversation_uid": "conv",
        "snapshot_id": "snap",
        "created_at": 1.0,
        "expires_at": 2.0,
        "consumer_session_id": "worker",
    })
    assert "handoff_id" not in result
    assert result["raw_capability_returned"] is False
    assert "secret-bearer" not in str(result)
