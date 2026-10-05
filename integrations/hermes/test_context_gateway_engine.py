from __future__ import annotations

from pathlib import Path
import json
import os
import sys
from unittest.mock import patch
import urllib.request


def _engine():
    hermes_root = Path(os.environ.get("HERMES_ROOT", "/home/hermes/.hermes"))
    sys.path.insert(0, "/home/hermes/.hermes/hermes-agent")
    target = hermes_root / "plugins" / "context-gateway" / "__init__.py"
    if not target.exists():
        import pytest
        pytest.skip("Hermes Gateway context engine is not installed")

    import importlib.util
    spec = importlib.util.spec_from_file_location("context_gateway_engine_test", target)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GatewayContextEngine()


def test_gateway_context_engine_loads_and_retrieves(monkeypatch):
    monkeypatch.setenv('UNIVERSAL_CONTEXT_GATEWAY_MODE', 'search')
    monkeypatch.delenv('UNIVERSAL_CONTEXT_GATEWAY_CONVERSATION_UID', raising=False)

    class _Response:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self):
            return json.dumps({'evidence': [{'provider': 'chatgpt', 'account_id': 'camofox-human-login', 'id': 'conversation-1', 'excerpt': 'historical engineering loop context'}]}).encode()

    monkeypatch.setattr(urllib.request, 'urlopen', lambda *args, **kwargs: _Response())
    engine = _engine()
    message = {
        "role": "user",
        "content": "Lanjutin pembahasan engineering loop yang terakhir.",
    }
    selected = engine.select_context(
        [{"role": "system", "content": "test"}, message.copy()],
        incoming_message=message,
        conversation_messages=[message],
        budget_tokens=100_000,
    )

    assert selected is not None
    assert "UNIVERSAL CONTEXT GATEWAY" in selected[-1]["content"]
    assert "camofox-human-login" in selected[-1]["content"]
    assert "CURRENT USER REQUEST" in selected[-1]["content"]


def test_gateway_context_engine_does_not_clobber_hermes_provider():
    engine = _engine()
    engine.update_model(
        model="mock",
        context_length=128_000,
        base_url="http://127.0.0.1:8788/v1",
        api_key="test",
        provider="custom:mock",
        api_mode="chat_completions",
    )

    assert engine.provider == "custom:mock"
    assert engine.gateway_provider == "chatgpt"
    assert engine.gateway_account == "camofox-human-login"


def test_gateway_context_engine_recovers_continuation_ack(monkeypatch):
    monkeypatch.setenv('UNIVERSAL_CONTEXT_GATEWAY_MODE', 'search')
    monkeypatch.delenv('UNIVERSAL_CONTEXT_GATEWAY_CONVERSATION_UID', raising=False)
    engine = _engine()
    prior = {
        "role": "assistant",
        "content": "Previous plan: run the golden continuity proof.",
    }
    incoming = {"role": "user", "content": "Gas bro! Thinking"}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "evidence": [
                        {
                            "provider": "chatgpt",
                            "account_id": "camofox-human-login",
                            "id": "conversation-1",
                            "snapshot_id": "snapshot-1",
                            "message_id": "message-1",
                            "excerpt": "Previous plan: run the golden continuity proof.",
                        }
                    ]
                }
            ).encode()

    with patch.object(urllib.request, "urlopen", return_value=_Response()) as opened:
        selected = engine.select_context(
            [prior.copy(), incoming.copy()],
            incoming_message=incoming,
            conversation_messages=[prior, incoming],
            budget_tokens=100_000,
        )

    opened.assert_called_once()
    request = opened.call_args.args[0]
    sent_query = json.loads(request.data.decode())["query"]
    assert sent_query == "Previous plan: run the golden continuity proof."
    assert selected is not None
    content = selected[-1]["content"]
    assert "UNIVERSAL CONTEXT GATEWAY" in content
    assert "CURRENT USER REQUEST" in content
    assert "Continuation acknowledgement detected." in content
