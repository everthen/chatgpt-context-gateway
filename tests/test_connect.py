from pathlib import Path

import pytest

from context_gateway.connect import CredentialImportError, parse_curl_capture, save_credentials


def test_parse_curl_capture_extracts_supported_headers():
    curl = """curl 'https://chatgpt.com/backend-api/gizmos/snorlax/sidebar' \
-H 'Authorization: Bearer token-123' \
-H 'chatgpt-account-id: acct-456' \
-H 'Cookie: oai-did=abc; __Secure-next-auth.session-token=xyz' \
-H 'User-Agent: TestBrowser/1.0' \
--compressed"""
    values = parse_curl_capture(curl)
    assert values["OAI_AUTHZ_TOKEN"] == "token-123"
    assert values["OAI_ACC_ID"] == "acct-456"
    assert values["OAI_COOKIE"] == "oai-did=abc; __Secure-next-auth.session-token=xyz"
    assert values["CHATGPT_USER_AGENT"] == "TestBrowser/1.0"


def test_parse_curl_capture_accepts_cookie_only():
    curl = "curl 'https://chatgpt.com/backend-api/conversations' -H 'cookie: session=abc'"
    values = parse_curl_capture(curl)
    assert values["OAI_AUTHZ_TOKEN"] == ""
    assert values["OAI_COOKIE"] == "session=abc"


@pytest.mark.parametrize(
    "curl",
    [
        "curl 'http://chatgpt.com/backend-api/conversations' -H 'cookie: x=y'",
        "curl 'https://evil.example/backend-api/conversations' -H 'cookie: x=y'",
        "curl 'https://chatgpt.com/backend-api/conversations'",
        "wget 'https://chatgpt.com/backend-api/conversations'",
    ],
)
def test_parse_curl_capture_rejects_unsafe_or_incomplete_input(curl):
    with pytest.raises(CredentialImportError):
        parse_curl_capture(curl)


def test_save_credentials_uses_restrictive_permissions(tmp_path: Path):
    path = save_credentials(
        {
            "OAI_AUTHZ_TOKEN": "token-123",
            "OAI_ACC_ID": "acct-456",
            "OAI_COOKIE": "session=abc",
        },
        tmp_path / "nested" / "env",
    )
    assert path.read_text(encoding="utf-8").count("\nOAI_") >= 0
    assert "token-123" in path.read_text(encoding="utf-8")
    assert oct(path.stat().st_mode & 0o777) == "0o600"
