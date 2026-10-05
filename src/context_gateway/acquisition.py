from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .camofox import CamofoxObservation
from .config import get_raw_dir, safe_project_name
from .db import ArchiveDB
from .normalize import make_record


def ingest_conversation_payload(
    payload: dict[str, Any],
    *,
    project_id: str,
    project_name: str,
    provider: str = "chatgpt",
    account_id: str = "default",
    acquisition_method: str = "manual",
    db: ArchiveDB,
    raw_dir: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("conversation payload must be an object")

    raw_dir = Path(raw_dir or get_raw_dir())
    conversation_id = payload.get("id") or payload.get("conversation_id")
    if not conversation_id:
        raise ValueError("conversation payload is missing conversation id")

    record = make_record(
        payload,
        project_id=project_id,
        project_name=project_name,
        raw_path="",
        provider=provider,
        account_id=account_id,
        source=acquisition_method,
        captured_at=time.time(),
    )

    current = db.current_snapshot_for_record(record)
    if current and current["raw_hash"] == record["raw_hash"]:
        record["raw_path"] = current["raw_path"]
        db.upsert_conversation(record)
    else:
        seq = db.next_snapshot_seq(record)
        project_key = safe_project_name(project_name)
        conversation_key = safe_project_name(str(conversation_id))
        raw_path = (
            raw_dir
            / safe_project_name(provider)
            / safe_project_name(account_id)
            / project_key
            / conversation_key
            / f"snapshot-{seq:03d}.json"
        )
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        record["raw_path"] = str(raw_path)
        db.upsert_conversation(record)

    uid = db._conversation_uid_from_record(record)
    snapshot = db.current_snapshot(uid)
    checkpoint = {
        "provider": provider,
        "account_id": account_id,
        "scope_type": "conversation",
        "scope_id": str(conversation_id),
        "method": acquisition_method,
        "status": "success",
        "last_success_at": time.time(),
        "last_seen_remote_at": record.get("update_time"),
        "cursor": None,
        "last_error": None,
    }
    db.upsert_acquisition_checkpoint(checkpoint)
    return {
        "conversation_uid": uid,
        "snapshot_id": snapshot["snapshot_id"] if snapshot else None,
        "raw_path": record["raw_path"],
        "acquisition": checkpoint,
    }


def ingest_camofox_observation(
    observation: CamofoxObservation,
    *,
    project_id: str,
    project_name: str,
    db: ArchiveDB,
    raw_dir: Path | None = None,
    require_complete: bool = True,
) -> dict[str, Any]:
    if require_complete and not observation.complete:
        raise ValueError(
            "Camofox observation is incomplete; refusing to promote it to historical evidence"
        )

    return ingest_conversation_payload(
        observation.to_payload(),
        project_id=project_id,
        project_name=project_name,
        provider=observation.provider,
        account_id=observation.account_id,
        acquisition_method="camofox-browser",
        db=db,
        raw_dir=raw_dir,
    )
