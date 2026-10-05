from __future__ import annotations

from pathlib import Path


def test_gateway_context_engine_loads_and_retrieves():
    import os
    import sys

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
    engine = module.GatewayContextEngine()

    message = {"role": "user", "content": "Lanjutin pembahasan engineering loop yang terakhir."}
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
