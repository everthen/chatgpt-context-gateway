from pathlib import Path

import pytest

from context_gateway.worker_dispatch import dispatch_handoff_worker


class _FakeProcess:
    pid = 4321

    def wait(self):
        return 0


def test_dispatch_handoff_worker_transfers_capability_safely(tmp_path, monkeypatch):
    calls = []

    observed = {}

    def fake_popen(argv, **kwargs):
        calls.append((argv, kwargs))
        query_path = Path(argv[argv.index("--query-file") + 1])
        observed["query"] = query_path.read_text()
        observed["mode"] = query_path.stat().st_mode & 0o777
        return _FakeProcess()

    monkeypatch.setenv("PARENT_SECRET_TOKEN", "should-not-cross")
    monkeypatch.setattr("context_gateway.worker_dispatch.subprocess.Popen", fake_popen)

    result = dispatch_handoff_worker(
        handoff_id="opaque-handoff",
        consumer_session_id="consumer-1",
        prompt='Answer exactly "PASS" after using the handed-off evidence.',
        hermes_bin="/bin/echo",
        worker_root=tmp_path,
        session_title="Dispatch Proof",
    )

    assert result["status"] == "started"
    assert result["pid"] == 4321
    assert result["handoff_capability_transferred"] is True
    assert result["consumer_session_id"] == "consumer-1"
    assert len(calls) == 1

    argv, kwargs = calls[0]
    assert argv[:4] == ["/bin/echo", "chat", "-Q", "--query-file"]
    assert "--format" in argv
    assert argv[argv.index("--format") + 1] == "stream-json"
    assert "--toolsets" in argv
    assert argv[argv.index("--toolsets") + 1] == "context_engine"
    assert observed["query"] == 'Answer exactly "PASS" after using the handed-off evidence.'
    assert observed["mode"] == 0o600
    assert result["toolsets"] == ["context_engine"]
    assert kwargs["env"]["UNIVERSAL_CONTEXT_GATEWAY_HANDOFF_ID"] == "opaque-handoff"
    assert kwargs["env"]["UNIVERSAL_CONTEXT_GATEWAY_HANDOFF_CONSUMER_SESSION_ID"] == "consumer-1"
    assert "PARENT_SECRET_TOKEN" not in kwargs["env"]
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is not None

    meta = Path(result["log_path"]).parent / "dispatch.json"
    assert meta.exists()


def test_dispatch_requires_prompt(tmp_path):
    with pytest.raises(ValueError, match="worker prompt is required"):
        dispatch_handoff_worker(
            handoff_id="opaque-handoff",
            consumer_session_id="consumer-1",
            prompt="",
            hermes_bin="/bin/echo",
            worker_root=tmp_path,
        )


def test_wait_for_handoff_worker_returns_model_answer(tmp_path):
    from context_gateway.worker_dispatch import wait_for_handoff_worker

    work = tmp_path / "dispatch-1"
    work.mkdir()
    log = work / "worker.log"
    meta = work / "dispatch.json"
    log.write_text(
        "GOLDEN-E2E-PASS\n\nsession_id: 20261005_test\n",
        encoding="utf-8",
    )
    meta.write_text(
        '{"dispatch_id":"dispatch-1","status":"completed","exit_code":0,"finished_at":123.0}',
        encoding="utf-8",
    )

    result = wait_for_handoff_worker(
        {
            "dispatch_id": "dispatch-1",
            "log_path": str(log),
        },
        timeout_seconds=0.1,
        poll_seconds=0.01,
    )

    assert result["status"] == "completed"
    assert result["output"] == "GOLDEN-E2E-PASS"
    assert result["session_id"] == "20261005_test"
    assert result["exit_code"] == 0
