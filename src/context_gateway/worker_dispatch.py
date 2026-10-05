from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Iterable


DEFAULT_HERMES_BIN = "/home/hermes/.hermes/venv/bin/hermes"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8795"
DEFAULT_WORKER_ROOT = Path("/home/hermes/.hermes/runtime/context-handoff-workers")
DEFAULT_RETENTION_SECONDS = 3600
DEFAULT_MAX_TURNS = 60
DEFAULT_RUN_BUDGET_SECONDS = 240.0

ALLOWED_WORKER_TOOLSETS = frozenset({
    "context_engine", "web", "search", "file", "terminal", "browser",
    "skills", "code_execution", "delegation", "vision", "image_gen",
    "computer_use", "todo",
})
DENIED_WORKER_TOOLSETS = frozenset({
    "hermes-cli", "cronjob", "connections", "memory", "kanban",
    "homeassistant", "discord", "discord_admin", "yuanbao",
    "feishu_doc", "feishu_drive", "tts",
})


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


def _open_secure_append(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    return os.fdopen(fd, "a", encoding="utf-8", buffering=1)


def _normalize_toolsets(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return ["context_engine"]
    raw = value.split(",") if isinstance(value, str) else list(value)
    result: list[str] = []
    for item in raw:
        name = str(item).strip()
        if not name:
            continue
        if name in DENIED_WORKER_TOOLSETS:
            raise ValueError(f"worker toolset is not permitted: {name}")
        if name not in ALLOWED_WORKER_TOOLSETS:
            raise ValueError(f"unknown worker toolset: {name}")
        if name not in result:
            result.append(name)
    if not result:
        raise ValueError("worker toolsets must not be empty")
    return result


def _cleanup_old_workdirs(root: Path, *, max_age_seconds: float) -> None:
    cutoff = time.time() - max_age_seconds
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            metadata = _read_json(entry / "dispatch.json")
            if metadata and str(metadata.get("status")) in {"started", "terminating"}:
                continue
            for child in entry.iterdir():
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
            entry.rmdir()
        except OSError:
            continue


def _safe_update_meta(path: Path, updates: dict[str, Any]) -> None:
    record = _read_json(path) or {}
    record.update(updates)
    try:
        _write_secret_file(path, json.dumps(record, indent=2))
    except OSError:
        pass


def _terminate_process_group(pid: int, *, grace_seconds: float = 5.0) -> dict[str, Any]:
    outcome = {"requested": True, "sigterm": False, "sigkill": False, "gone": False}
    try:
        os.killpg(pid, signal.SIGTERM)
        outcome["sigterm"] = True
    except ProcessLookupError:
        outcome["gone"] = True
        return outcome
    except OSError:
        return outcome
    deadline = time.monotonic() + max(grace_seconds, 0.0)
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            outcome["gone"] = True
            return outcome
        except OSError:
            break
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
        outcome["sigkill"] = True
    except ProcessLookupError:
        outcome["gone"] = True
    except OSError:
        pass
    return outcome


def _worker_environment(
    *,
    handoff_id: str,
    consumer_session_id: str,
    gateway_url: str,
) -> dict[str, str]:
    # Keep secrets and unrelated parent-process configuration out of worker env.
    safe_names = {
        "PATH", "HOME", "HERMES_HOME", "LANG", "LC_ALL", "LC_CTYPE",
        "TZ", "TERM", "TMPDIR", "NO_COLOR",
    }
    env = {key: value for key, value in os.environ.items() if key in safe_names}
    env["HOME"] = "/home/hermes"
    env["HERMES_HOME"] = "/home/hermes/.hermes"
    env["UNIVERSAL_CONTEXT_GATEWAY_URL"] = gateway_url.rstrip("/")
    env["UNIVERSAL_CONTEXT_GATEWAY_HANDOFF_ID"] = handoff_id
    env["UNIVERSAL_CONTEXT_GATEWAY_HANDOFF_CONSUMER_SESSION_ID"] = consumer_session_id
    env["HERMES_SESSION_SOURCE"] = "tool"
    env["HERMES_SESSION_SOURCE_EXPLICIT"] = "1"
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
    toolsets: str | Iterable[str] | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    run_budget_seconds: float = DEFAULT_RUN_BUDGET_SECONDS,
    retention_seconds: int = DEFAULT_RETENTION_SECONDS,
) -> dict[str, Any]:
    """Spawn one finite Hermes worker with an explicit capability scope."""
    if not handoff_id.strip():
        raise ValueError("handoff_id is required")
    if not consumer_session_id.strip():
        raise ValueError("consumer_session_id is required")
    if not prompt.strip():
        raise ValueError("worker prompt is required")

    normalized_toolsets = _normalize_toolsets(toolsets)
    max_turns = max(1, min(int(max_turns), 500))
    run_budget_seconds = max(1.0, min(float(run_budget_seconds), 3600.0))
    retention_seconds = max(0, min(int(retention_seconds), 604800))

    root = _secure_dir(Path(worker_root))
    _cleanup_old_workdirs(root, max_age_seconds=DEFAULT_RETENTION_SECONDS)
    dispatch_id = secrets.token_urlsafe(18)
    work_dir = _secure_dir(root / dispatch_id)
    query_path = work_dir / "query.txt"
    stdout_path = work_dir / "worker.stdout.jsonl"
    stderr_path = work_dir / "worker.stderr.log"
    meta_path = work_dir / "dispatch.json"

    _write_secret_file(query_path, prompt)
    hermes = hermes_bin or os.environ.get("HERMES_BIN") or DEFAULT_HERMES_BIN
    if not Path(hermes).is_file():
        query_path.unlink(missing_ok=True)
        work_dir.rmdir()
        raise FileNotFoundError(f"Hermes binary not found: {hermes}")

    title = (session_title or f"UCG Handoff {dispatch_id[:10]}").strip()
    argv = [
        hermes, "chat", "-Q",
        "--query-file", str(query_path),
        "--format", "stream-json",
        "--toolsets", ",".join(normalized_toolsets),
        "--max-turns", str(max_turns),
        "--run-budget", str(run_budget_seconds),
        "--source", "tool",
    ]
    env = _worker_environment(
        handoff_id=handoff_id,
        consumer_session_id=consumer_session_id,
        gateway_url=gateway_url,
    )

    stdout_handle = _open_secure_append(stdout_path)
    stderr_handle = _open_secure_append(stderr_path)
    try:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            cwd="/home/hermes",
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    except BaseException:
        stdout_handle.close()
        stderr_handle.close()
        query_path.unlink(missing_ok=True)
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)
        work_dir.rmdir()
        raise
    else:
        stdout_handle.close()
        stderr_handle.close()

    metadata = {
        "dispatch_id": dispatch_id,
        "status": "started",
        "pid": process.pid,
        "handoff_capability_transferred": True,
        "consumer_session_id": consumer_session_id,
        "session_title": title,
        "toolsets": normalized_toolsets,
        "max_turns": max_turns,
        "run_budget_seconds": run_budget_seconds,
        "retention_seconds": retention_seconds,
        "created_at": time.time(),
        "query_path": str(query_path),
        "log_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    try:
        _write_secret_file(meta_path, json.dumps(metadata, indent=2))
    except BaseException:
        _terminate_process_group(process.pid)
        query_path.unlink(missing_ok=True)
        stdout_path.unlink(missing_ok=True)
        stderr_path.unlink(missing_ok=True)
        work_dir.rmdir()
        raise

    def _reap_and_cleanup() -> None:
        record = dict(metadata)
        try:
            rc = process.wait()
            record["status"] = (
                "cancelled" if record.get("cancel_requested_at") is not None
                else ("completed" if rc == 0 else "failed")
            )
            record["exit_code"] = rc
            record["finished_at"] = time.time()
            _write_secret_file(meta_path, json.dumps(record, indent=2))
        except Exception:
            return
        finally:
            query_path.unlink(missing_ok=True)

        if retention_seconds == 0:
            for child in (stdout_path, stderr_path, meta_path):
                child.unlink(missing_ok=True)
            try:
                work_dir.rmdir()
            except OSError:
                pass
            return

        def _expire_artifacts() -> None:
            time.sleep(retention_seconds)
            for child in (stdout_path, stderr_path, meta_path, query_path):
                child.unlink(missing_ok=True)
            try:
                work_dir.rmdir()
            except OSError:
                pass

        threading.Thread(
            target=_expire_artifacts,
            name=f"ucg-expire-{dispatch_id[:8]}",
            daemon=True,
        ).start()

    threading.Thread(
        target=_reap_and_cleanup,
        name=f"ucg-handoff-{dispatch_id[:8]}",
        daemon=True,
    ).start()
    return metadata


_SESSION_ID_RE = re.compile(r"(?m)^session_id:\s*(\S+)\s*$")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _read_bounded(path: Path, *, max_chars: int = 24_000) -> str:
    try:
        output = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return output if len(output) <= max_chars else output[-max_chars:]


def _parse_stream_json(stdout: str) -> dict[str, Any]:
    terminal: dict[str, Any] | None = None
    session_id: str | None = None
    text_deltas: list[str] = []
    parsed_lines = 0

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed_lines += 1
        if event.get("type") == "system" and event.get("subtype") == "init":
            session_id = str(event.get("session_id") or "") or session_id
        elif event.get("type") == "text":
            delta = str(event.get("text") or "")
            if delta:
                text_deltas.append(delta)
        elif event.get("type") == "result":
            terminal = dict(event)
            session_id = str(event.get("session_id") or "") or session_id

    if terminal is not None:
        text = str(terminal.get("text") or "")
        if not text and text_deltas:
            text = "".join(text_deltas).strip()
        return {
            "parsed": True,
            "session_id": session_id,
            "exit_code": terminal.get("exit_code"),
            "output": text.strip(),
            "terminal": terminal,
            "parsed_lines": parsed_lines,
        }

    match = _SESSION_ID_RE.search(stdout)
    return {
        "parsed": False,
        "session_id": match.group(1) if match else session_id,
        "exit_code": None,
        "output": _SESSION_ID_RE.sub("", stdout).strip(),
        "terminal": None,
        "parsed_lines": parsed_lines,
    }


def wait_for_handoff_worker(
    dispatch: dict[str, Any],
    *,
    timeout_seconds: float = 240.0,
    poll_seconds: float = 0.5,
    cancel_on_timeout: bool = True,
    terminate_grace_seconds: float = 5.0,
) -> dict[str, Any]:
    """Wait for a worker; timeout terminates the whole worker process group."""
    dispatch_id = str(dispatch.get("dispatch_id") or "").strip()
    if not dispatch_id:
        raise ValueError("dispatch_id is required")

    log_path = Path(str(dispatch.get("log_path") or ""))
    stderr_path = Path(str(dispatch.get("stderr_path") or log_path.with_name("worker.stderr.log")))
    meta_path = log_path.with_name("dispatch.json")
    deadline = time.monotonic() + max(timeout_seconds, 0.0)

    while True:
        meta = _read_json(meta_path) or dispatch
        status = str(meta.get("status") or "started")
        if status in {"completed", "failed", "cancelled"}:
            stdout = _read_bounded(log_path)
            parsed = _parse_stream_json(stdout)
            return {
                "dispatch_id": dispatch_id,
                "status": status,
                "exit_code": meta.get("exit_code", parsed.get("exit_code")),
                "session_id": parsed.get("session_id"),
                "output": parsed.get("output", ""),
                "output_raw": _read_bounded(log_path),
                "stderr": _read_bounded(stderr_path, max_chars=8_000),
                "finished_at": meta.get("finished_at"),
                "worker_pid": meta.get("pid"),
                "toolsets": meta.get("toolsets"),
            }

        if time.monotonic() >= deadline:
            pid = int(meta.get("pid") or dispatch.get("pid") or 0)
            termination = (
                _terminate_process_group(pid, grace_seconds=terminate_grace_seconds)
                if cancel_on_timeout and pid > 0
                else {"requested": False, "gone": False}
            )
            _safe_update_meta(
                meta_path,
                {
                    "status": "terminating" if termination.get("requested") else "timeout",
                    "cancel_requested_at": time.time() if termination.get("requested") else None,
                    "termination": termination,
                },
            )
            return {
                "dispatch_id": dispatch_id,
                "status": "cancelled" if termination.get("requested") else "timeout",
                "exit_code": None,
                "session_id": None,
                "output": "",
                "output_raw": "",
                "stderr": "",
                "finished_at": None,
                "worker_pid": pid or None,
                "termination": termination,
                "toolsets": meta.get("toolsets"),
            }
        time.sleep(max(poll_seconds, 0.05))
