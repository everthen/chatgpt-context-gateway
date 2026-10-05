import json
from pathlib import Path
from typing import Any

from .client import ChatGPTClient
from .config import get_db_path, get_raw_dir, safe_project_name
from .db import ArchiveDB
from .normalize import make_record

def sync_project(
    project_name: str,
    client: ChatGPTClient | None = None,
    db: ArchiveDB | None = None,
    raw_dir: Path | None = None,
    env_file: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Sync all conversations for a given project name or ID.

    1. Resolves project from ChatGPT or local DB.
    2. Fetches full conversation payloads.
    3. Saves raw JSON files to data/raw/<provider>/<account>/<safe_project>/<conversation_id>.json.
    4. Indexes metadata and extracted text into SQLite.
    """
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
        local_projects = db.projects()
        for p in local_projects:
            if p.get("id") == project_name or p.get("name", "").strip().lower() == project_name.strip().lower():
                target_project = p
                break

    if target_project is None:
        target_project = {"id": project_name, "name": project_name}

    project_id = target_project["id"]
    canonical_name = target_project.get("name") or project_name

    provider = "chatgpt"
    account_id = getattr(client, "account_id", None) or "default"
    safe_provider = safe_project_name(provider)
    safe_account = safe_project_name(account_id)
    safe_proj = safe_project_name(canonical_name)
    proj_raw_dir = raw_dir / safe_provider / safe_account / safe_proj
    proj_raw_dir.mkdir(parents=True, exist_ok=True)

    offset = 0
    limit = 28
    synced_records: list[dict[str, Any]] = []

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

            raw_file_path = proj_raw_dir / f"{cid}.json"
            raw_file_path.write_text(
                json.dumps(full_conv, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            record = make_record(
                full_conv,
                project_id=project_id,
                project_name=canonical_name,
                raw_path=str(raw_file_path),
                provider=provider,
                account_id=account_id,
                source=provider,
            )
            db.upsert_conversation(record)
            synced_records.append(record)

        offset += len(items)
        total = resp.get("total")
        if total is not None and offset >= total:
            break
        if len(items) < limit:
            break

    return synced_records

def sync_projects(
    client: ChatGPTClient | None = None,
    db: ArchiveDB | None = None,
    raw_dir: Path | None = None,
    env_file: str | Path | None = None,
) -> dict[str, int]:
    """Sync all projects available on the authenticated ChatGPT account."""
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
