from __future__ import annotations

import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
import re


DEFAULT_HERMES_BIN = "/home/hermes/.hermes/venv/bin/hermes"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8795"
DEFAULT_WORKER_ROOT = Path("/home/hermes/.hermes/runtime/context-handoff-workers")


def _secure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_secret_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    path.chmod(0o600)


def _worker_environment(
    *,
    handoff_id: str,
    consumer_session_id: str,
    gateway_url: str,
) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = "/home/hermes"
    env["HERMES_HOME"] = "/home/hermes/.hermes"
    env["UNIVERSAL_CONTEXT_GATEWAY_URL"] = gateway_url.rstrip("/")
    env["UNIVERSAL_CONTEXT_GATEWAY_HANDOFF_ID"] = handoff_id
    env["UNIVERSAL_CONTEXT_GATEWAY_HANDOFF_CONSUMER_SESSION_ID"] = consumer_session_id
    return env


def dispatch_handoff_worker(
    *,
    handoff_id: str,
    consumer_session_id: str,
    prompt: str,
    gateway_url: str = DEFAULT_GATEWAY_URL,
    hermes_bin: str | None = None,
    worker_root: str | Path = DEFAULT_WORKER_ROOT,
    session_title: str | None = None,
) -> dict[str, Any]:
    """Spawn one finite Hermes worker whose first turn redeems the opaque handoff."""
    if not handoff_id.strip():
        raise ValueError("handoff_id is required")
    if not consumer_session_id.strip():
        raise ValueError("consumer_session_id is required")
    if not prompt.strip():
        raise ValueError("worker prompt is required")

    root = _secure_dir(Path(worker_root))
    dispatch_id = secrets.token_urlsafe(18)
    work_dir = _secure_dir(root / dispatch_id)
    query_path = work_dir / "query.txt"
    log_path = work_dir / "worker.log"
    meta_path = work_dir / "dispatch.json"

    _write_secret_file(query_path, prompt)
    hermes = hermes_bin or os.environ.get("HERMES_BIN") or DEFAULT_HERMES_BIN
    if not Path(hermes).is_file():
        raise FileNotFoundError(f"Hermes binary not found: {hermes}")

    title = (session_title or f"UCG Handoff {dispatch_id[:10]}").strip()
    argv = [
        hermes,
        "chat",
        "-Q",
        "--query-file",
        str(query_path),
    ]
    env = _worker_environment(
        handoff_id=handoff_id,
        consumer_session_id=consumer_session_id,
        gateway_url=gateway_url,
    )

    log_handle = open(log_path, "a", encoding="utf-8", buffering=1)
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd="/home/hermes",
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    except BaseException:
        log_handle.close()
        raise
    else:
        log_handle.close()

    metadata = {
        "dispatch_id": dispatch_id,
        "status": "started",
        "pid": process.pid,
        "handoff_capability_transferred": True,
        "consumer_session_id": consumer_session_id,
        "session_title": title,
        "created_at": time.time(),
        "query_path": str(query_path),
        "log_path": str(log_path),
    }
    _write_secret_file(meta_path, json.dumps(metadata, indent=2))

    def _reap_and_cleanup() -> None:
        record = dict(metadata)
        try:
            rc = process.wait()
            record["status"] = "completed" if rc == 0 else "failed"
            record["exit_code"] = rc
            record["finished_at"] = time.time()
            _write_secret_file(meta_path, json.dumps(record, indent=2))
        except Exception:
            return
        finally:
            try:
                query_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    threading.Thread(
        target=_reap_and_cleanup,
        name=f"ucg-handoff-{dispatch_id[:8]}",
        daemon=True,
    ).start()
    return metadata


_SESSION_ID_RE = re.compile(r"(?m)^session_id:\s*(\S+)\s*$")
_RESULT_MAX_CHARS = 24000


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _read_worker_output(path: Path, *, max_chars: int = _RESULT_MAX_CHARS) -> str:
    try:
        output = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(output) > max_chars:
        return output[-max_chars:]
    return output


def wait_for_handoff_worker(
    dispatch: dict[str, Any],
    *,
    timeout_seconds: float = 240.0,
    poll_seconds: float = 0.5,
) -> dict[str, Any]:
    """Wait for a dispatched worker and return its bounded model output."""
    dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
    if not dispatch_id:
        raise ValueError("dispatch_id is required")

    meta_path = Path(str(dispatch.get("log_path") or "")).with_name("dispatch.json")
    log_path = Path(str(dispatch.get("log_path") or ""))
    deadline = time.monotonic() + max(timeout_seconds, 0.0)

    while True:
        meta = _read_json(meta_path) or dispatch
        status = str(meta.get("status") or "started")
        if status in {"completed", "failed"}:
            output = _read_worker_output(log_path)
            session_match = _SESSION_ID_RE.search(output)
            session_id = session_match.group(1) if session_match else None
            answer = _SESSION_ID_RE.sub("", output).strip()
            return {
                "dispatch_id": dispatch_id,
                "status": status,
                "exit_code": meta.get("exit_code"),
                "session_id": session_id,
                "output": answer,
                "output_raw": output,
                "finished_at": meta.get("finished_at"),
            }

        if time.monotonic() >= deadline:
            return {
                "dispatch_id": dispatch_id,
                "status": "timeout",
                "exit_code": None,
                "session_id": None,
                "output": "",
                "output_raw": "",
            }
        time.sleep(max(poll_seconds, 0.05))
