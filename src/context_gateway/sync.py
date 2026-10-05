import json
import time
from pathlib import Path
from typing import Any

from .client import ChatGPTClient
from .config import get_db_path, get_raw_dir, safe_project_name
from .db import ArchiveDB
from .normalize import make_record


def _snapshot_path(
    raw_dir: Path,
    provider: str,
    account_id: str,
    project_name: str,
    conversation_id: str,
    seq: int,
) -> Path:
    project_key = safe_project_name(project_name)
    conversation_key = safe_project_name(conversation_id)
    return (
        raw_dir
        / safe_project_name(provider)
        / safe_project_name(account_id)
        / project_key
        / conversation_key
        / f"snapshot-{seq:03d}.json"
    )


def sync_project(
    project_name: str,
    client: ChatGPTClient | None = None,
    db: ArchiveDB | None = None,
    raw_dir: Path | None = None,
    env_file: str | Path | None = None,
) -> list[dict[str, Any]]:
    if client is None:
        client = ChatGPTClient(env_file=env_file)
    if db is None:
        db = ArchiveDB(get_db_path())
    if raw_dir is None:
        raw_dir = get_raw_dir()

    raw_dir = Path(raw_dir)
    target_project: dict[str, Any] | None = None

    try:
        remote_projects = client.list_projects()
    except Exception:
        remote_projects = []

    for p in remote_projects:
        if p.get("id") == project_name or p.get("name", "").strip().lower() == project_name.strip().lower():
            target_project = p
            db.upsert_project(p)
            break

    if target_project is None:
        for p in db.projects():
            if p.get("project_uid") == project_name or p.get("id") == project_name or p.get("name", "").strip().lower() == project_name.strip().lower():
                target_project = p
                break

    if target_project is None:
        target_project = {"id": project_name, "name": project_name}

    project_id = target_project["id"]
    canonical_name = target_project.get("name") or project_name
    provider = getattr(client, "provider", None) or "chatgpt"
    account_id = getattr(client, "account_id", None) or "default"

    synced_records: list[dict[str, Any]] = []
    offset = 0
    limit = 50

    while True:
        resp = client.list_conversations(project_id=project_id, offset=offset, limit=limit)
        items = resp.get("items") or []
        if not items:
            break

        for item in items:
            cid = item.get("id") or item.get("conversation_id")
            if not cid:
                continue

            full_conv = client.get_conversation(cid)
            record = make_record(
                full_conv,
                project_id=project_id,
                project_name=canonical_name,
                raw_path="",
                provider=provider,
                account_id=account_id,
                source=provider,
                captured_at=time.time(),
            )

            current = db.current_snapshot_for_record(record)
            if current and current["raw_hash"] == record["raw_hash"]:
                record["raw_path"] = current["raw_path"]
            else:
                seq = db.next_snapshot_seq(record)
                raw_file_path = _snapshot_path(
                    raw_dir,
                    provider,
                    account_id,
                    canonical_name,
                    str(cid),
                    seq,
                )
                raw_file_path.parent.mkdir(parents=True, exist_ok=True)
                raw_file_path.write_text(
                    json.dumps(full_conv, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                record["raw_path"] = str(raw_file_path)

            db.upsert_conversation(record)
            record["conversation_uid"] = db._conversation_uid_from_record(record)
            record["snapshot_id"] = db.current_snapshot(record["conversation_uid"])["snapshot_id"]
            synced_records.append(record)

        offset += len(items)
        total = resp.get("total")
        if total is not None and offset >= total:
            break
        if len(items) < limit:
            break

    db.upsert_acquisition_checkpoint(
        {
            "provider": provider,
            "account_id": account_id,
            "scope_type": "project",
            "scope_id": str(project_id),
            "method": "chatgpt-api",
            "status": "success",
            "cursor": None,
            "last_success_at": time.time(),
            "last_seen_remote_at": max(
                (
                    float(r.get("update_time"))
                    for r in synced_records
                    if r.get("update_time") is not None
                ),
                default=None,
            ),
            "last_error": None,
        }
    )
    return synced_records


def sync_projects(
    client: ChatGPTClient | None = None,
    db: ArchiveDB | None = None,
    raw_dir: Path | None = None,
    env_file: str | Path | None = None,
) -> dict[str, int]:
    if client is None:
        client = ChatGPTClient(env_file=env_file)
    if db is None:
        db = ArchiveDB(get_db_path())
    if raw_dir is None:
        raw_dir = get_raw_dir()

    projects = client.list_projects()
    summary: dict[str, int] = {}

    for p in projects:
        db.upsert_project(p)
        name = p.get("name") or p["id"]
        records = sync_project(
            project_name=name,
            client=client,
            db=db,
            raw_dir=raw_dir,
            env_file=env_file,
        )
        summary[name] = len(records)

    return summary
