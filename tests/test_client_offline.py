import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
import requests

from context_gateway.client import (
    AuthenticationError,
    ChatGPTClient,
    ChatGPTClientError,
    NotFoundError,
    RateLimitError,
    load_env_file,
)

def test_load_env_file(tmp_path: Path):
    env_content = """
    # Comment line
    CHATGPT_ACCESS_TOKEN="secret-test-token"
    CHATGPT_COOKIE='session=abc123xyz'
    export CHATGPT_BASE_URL=https://custom-api.example.com
    INVALID_LINE
    EMPTY_VAL=
    """
    env_file = tmp_path / "custom.env"
    env_file.write_text(env_content, encoding="utf-8")

    parsed = load_env_file(env_file)
    assert parsed["CHATGPT_ACCESS_TOKEN"] == "secret-test-token"
    assert parsed["CHATGPT_COOKIE"] == "session=abc123xyz"
    assert parsed["CHATGPT_BASE_URL"] == "https://custom-api.example.com"
    assert parsed["EMPTY_VAL"] == ""
    assert "# Comment line" not in parsed

def test_load_env_file_nonexistent():
    assert load_env_file(Path("/path/to/definitely/nonexistent.env")) == {}

def test_client_missing_credentials_raises_auth_error(monkeypatch):
    monkeypatch.delenv("CHATGPT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("CHATGPT_COOKIE", raising=False)
    monkeypatch.delenv("CHATGPT_ENV_FILE", raising=False)

    with pytest.raises(AuthenticationError) as exc_info:
        ChatGPTClient(env_file=Path("/nonexistent"))
    assert "No ChatGPT credentials found" in str(exc_info.value)

def test_client_headers_configured():
    client = ChatGPTClient(
        access_token="tok123",
        cookie="session=cook456",
        base_url="https://api.test.com",
    )
    assert client.session.headers["Authorization"] == "Bearer tok123"
    assert client.session.headers["Cookie"] == "session=cook456"
    assert "ChatGPTClient" in repr(client)
    assert "tok123" not in repr(client)
    assert "cook456" not in repr(client)

def test_client_methods_with_mock_request():
    client = ChatGPTClient(access_token="valid-token")

    def mock_request(method, path, **kwargs):
        if path == "projects":
            return {
                "items": [
                    {
                        "id": "proj-xyz",
                        "name": "Backend Gateway",
                        "created_at": "2024-01-01",
                        "updated_at": "2024-01-02",
                    }
                ]
            }
        elif path in ("projects/proj-xyz/conversations", "gizmos/proj-xyz/conversations"):
            return {
                "items": [{"id": "conv-001", "title": "First Conv"}],
                "total": 1,
                "cursor": None,
            }
        elif path == "conversation/conv-001":
            return {
                "id": "conv-001",
                "title": "First Conv",
                "mapping": {},
                "current_node": None,
            }
        raise NotFoundError(f"Unknown path: {path}")

    client._request = MagicMock(side_effect=mock_request)

    projects = client.list_projects()
    assert len(projects) == 1
    assert projects[0]["id"] == "proj-xyz"
    assert projects[0]["name"] == "Backend Gateway"

    convs = client.list_conversations(project_id="proj-xyz")
    assert len(convs["items"]) == 1
    assert convs["items"][0]["id"] == "conv-001"

    conv = client.get_conversation("conv-001")
    assert conv["id"] == "conv-001"
    assert conv["title"] == "First Conv"

def test_client_http_error_handling():
    client = ChatGPTClient(access_token="valid-token")

    resp_mock = MagicMock()
    resp_mock.status_code = 401
    resp_mock.text = "Unauthorized"
    client.session.request = MagicMock(return_value=resp_mock)

    with pytest.raises(AuthenticationError):
        client.get_conversation("some-id")

    resp_mock.status_code = 404
    resp_mock.text = "Not found"
    with pytest.raises(NotFoundError):
        client.get_conversation("some-id")

    resp_mock.status_code = 429
    resp_mock.text = "Rate limit"
    with pytest.raises(RateLimitError):
        client.get_conversation("some-id")
