from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .camofox import (
    CamofoxClient,
    CamofoxObservation,
    capture_latest_view,
    collect_conversation,
)
from .config import get_camofox_profile_id, get_raw_dir, safe_project_name
from .contracts import ContextRequest
from .continuity import context_request
from .db import ArchiveDB
from .normalize import make_record, stable_hash


AcquisitionAdapter = Callable[[ContextRequest, ArchiveDB], dict[str, Any]]


@dataclass(frozen=True)
class AcquisitionResult:
    status: str
    method: str
    provider: str
    account_id: str
    scope_type: str
    scope_id: str
    snapshot_id: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "provider": self.provider,
            "account_id": self.account_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "snapshot_id": self.snapshot_id,
            "error": self.error,
            "details": self.details or {},
        }


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
    observed_at: float | None = None,
    snapshot_complete: bool = True,
    completeness_reason: str | None = None,
    acquisition_attempt_id: str | None = None,
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
    observed_at = float(observed_at if observed_at is not None else time.time())
    record["observed_at"] = observed_at
    record["ingested_at"] = time.time()
    record["snapshot_completeness_status"] = "complete" if snapshot_complete else "partial"
    record["snapshot_completeness_reason"] = completeness_reason
    record["acquisition_method"] = acquisition_method
    record["acquisition_attempt_id"] = acquisition_attempt_id

    current = db.current_snapshot_for_record(record)
    if current and current["raw_hash"] == record["raw_hash"]:
        record["raw_path"] = current["raw_path"]
        upserted = db.upsert_conversation(
            record,
            promote_current=snapshot_complete,
        )
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
        upserted = db.upsert_conversation(
            record,
            promote_current=snapshot_complete,
        )

    uid = db._conversation_uid_from_record(record)
    snapshot = db.current_snapshot(uid)
    checkpoint = {
        "provider": provider,
        "account_id": account_id,
        "scope_type": "conversation",
        "scope_id": str(conversation_id),
        "method": acquisition_method,
        "status": "success" if snapshot_complete else "partial",
        "last_success_at": time.time() if snapshot_complete else None,
        "last_seen_remote_at": record.get("update_time"),
        "cursor": None,
        "last_error": None,
    }
    db.upsert_acquisition_checkpoint(checkpoint)
    return {
        "conversation_uid": uid,
        "snapshot_id": upserted["snapshot_id"],
        "current_snapshot_id": snapshot["snapshot_id"] if snapshot else None,
        "promoted_current": bool(upserted.get("promoted_current")),
        "observation_complete": snapshot_complete,
        "completeness_status": "complete" if snapshot_complete else "partial",
        "completeness_reason": completeness_reason,
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
        observed_at=observation.captured_at,
        snapshot_complete=observation.complete,
        completeness_reason=observation.completeness_reason,
    )


def _conversation_context(request: ContextRequest, db: ArchiveDB) -> tuple[str, str, str, str]:
    target = request.target
    current = request.current_session
    if target:
        conversation_uid = target.conversation_uid
        record = db.get(conversation_uid)
        if not record:
            raise ValueError(f"target conversation '{conversation_uid}' is not present in the local archive")
        conversation_id = str(record.get("id") or "")
    elif current:
        conversation_id = current.current_conversation_id
        conversation_uid = current.current_conversation_uid
        if not conversation_id:
            if conversation_uid and ":" in conversation_uid:
                conversation_id = conversation_uid.rsplit(":", 1)[-1]
            else:
                raise ValueError("current_session.current_conversation_id is required")
        record = db.get(conversation_uid or conversation_id)
    else:
        raise ValueError("live acquisition requires target or current_session")
    if not record:
        raise ValueError(f"conversation '{conversation_id}' is not present in the local archive")

    project_id = str(record.get("project_id") or request.scope.project or "")
    project_name = str(record.get("project_name") or "")
    if not project_id:
        raise ValueError("project id is required for Camofox ingestion")
    if not project_name:
        project_name = str(request.scope.project or "Untitled")

    return conversation_id, project_id, project_name, str(record.get("account_id") or "default")


def acquire_current_conversation_via_camofox(
    request: ContextRequest,
    db: ArchiveDB,
    *,
    client: CamofoxClient | None = None,
    user_id: str | None = None,
    max_scrolls: int = 60,
) -> dict[str, Any]:
    conversation_id, project_id, project_name, account_id = _conversation_context(request, db)
    profile_id = get_camofox_profile_id(user_id)
    client = client or CamofoxClient()

    tabs = client.list_tabs(profile_id)
    matching = [
        tab
        for tab in tabs
        if conversation_id in str(tab.get("url") or "")
    ]
    if not matching:
        raise ValueError(
            f"no authenticated Camofox tab found for conversation '{conversation_id}' "
            f"under acquisition profile '{profile_id}'"
        )

    tab = matching[0]
    tab_id = str(tab.get("tabId") or "")
    if not tab_id:
        raise ValueError("matching Camofox tab has no tabId")

    observation = collect_conversation(
        client,
        user_id=profile_id,
        tab_id=tab_id,
        account_id=account_id,
        max_scrolls=max_scrolls,
    )

    ingested = ingest_camofox_observation(
        observation,
        project_id=project_id,
        project_name=project_name,
        db=db,
        require_complete=not request.freshness.allow_partial,
    )
    return {
        "status": "success",
        "method": "camofox-browser",
        "conversation_id": conversation_id,
        "tab_id": tab_id,
        "observation_complete": observation.complete,
        "snapshot_id": ingested.get("snapshot_id"),
        "conversation_uid": ingested.get("conversation_uid"),
    }


def _live_tail_delta(
    current_messages: list[dict[str, Any]],
    observed_turns: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool, int]:
    """Return newly observed turns anchored to the current snapshot tail."""
    base = [(str(item.get("role") or ""), str(item.get("text") or "")) for item in current_messages]
    live = [(str(item.get("role") or ""), str(item.get("text") or "")) for item in observed_turns]
    if not live:
        return [], True, 0
    max_overlap = min(len(base), len(live))
    for overlap in range(max_overlap, 0, -1):
        if base[-overlap:] == live[:overlap]:
            delta = observed_turns[overlap:]
            return delta, True, overlap
    return observed_turns, False, 0


def acquire_hot_tail_via_camofox(
    request: ContextRequest,
    db: ArchiveDB,
    *,
    client: CamofoxClient | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Capture the currently rendered ChatGPT tail without scrolling.

    Hot capture is deliberately not promoted to the immutable current snapshot.
    It is a low-latency observation/cache layer used to catch recent turns.
    """
    conversation_id, _project_id, _project_name, account_id = _conversation_context(request, db)
    profile_id = get_camofox_profile_id(user_id)
    client = client or CamofoxClient()
    tabs = client.list_tabs(profile_id)
    matching = [tab for tab in tabs if conversation_id in str(tab.get("url") or "")]
    if not matching:
        raise ValueError(
            f"no authenticated Camofox tab found for conversation '{conversation_id}' "
            f"under acquisition profile '{profile_id}'"
        )
    tab_id = str(matching[0].get("tabId") or "")
    if not tab_id:
        raise ValueError("matching Camofox tab has no tabId")

    observation = capture_latest_view(
        client,
        user_id=profile_id,
        tab_id=tab_id,
        account_id=account_id,
    )
    turns = [
        {"role": turn.role, "text": turn.text, "observation_index": turn.observation_index}
        for turn in observation.turns
    ]
    record = db.get(conversation_id)
    if not record:
        raise ValueError(f"conversation '{conversation_id}' is not present in the local archive")
    conversation_uid = db._conversation_uid_from_record(record)
    hot = db.upsert_hot_observation(
        {
            "provider": observation.provider,
            "account_id": observation.account_id,
            "conversation_uid": conversation_uid,
            "conversation_id": observation.conversation_id,
            "method": "camofox-hot",
            "observed_at": observation.captured_at,
            "title": observation.title,
            "url": observation.url,
            "content_hash": stable_hash(turns),
            "turns": turns,
            "completeness_status": "partial",
            "completeness_reason": observation.completeness_reason,
        }
    )
    current = db.current_snapshot_for_record(record)
    current_messages = list((db.get_snapshot(current["snapshot_id"]) if current else {}).get("messages") or [])
    delta, anchored, overlap = _live_tail_delta(current_messages, turns)

    checkpoint = db.upsert_acquisition_checkpoint(
        {
            "provider": observation.provider,
            "account_id": observation.account_id,
            "scope_type": "conversation",
            "scope_id": observation.conversation_id,
            "method": "camofox-hot",
            "status": "observed",
            "cursor": hot.get("content_hash"),
            "last_success_at": observation.captured_at,
            "last_seen_remote_at": None,
            "last_error": None,
        }
    )
    return {
        "status": "hot_captured",
        "method": "camofox-hot",
        "conversation_id": conversation_id,
        "conversation_uid": conversation_uid,
        "tab_id": tab_id,
        "observation": {
            "observation_id": hot.get("observation_id"),
            "observed_at": observation.captured_at,
            "content_hash": hot.get("content_hash"),
            "turn_count": len(turns),
            "completeness_status": "partial",
            "completeness_reason": observation.completeness_reason,
        },
        "delta": {
            "anchored": anchored,
            "overlap_messages": overlap,
            "messages": delta,
        },
        "current_snapshot_id": current.get("snapshot_id") if current else None,
        "checkpoint": checkpoint,
        "raw_promoted": False,
    }


def run_hot_context_request(
    db: ArchiveDB,
    request: ContextRequest,
) -> dict[str, Any]:
    """Resolve current context and attach an unsealed hot viewport observation."""
    bundle = context_request(db, request)
    acquisition = bundle.get("acquisition") or {}
    if not request.freshness.allow_live_acquisition:
        return bundle
    if not request.target or request.target.snapshot != "current":
        bundle["acquisition"] = {
            **acquisition,
            "status": "hot_not_applicable",
            "reason": "hot capture requires a current conversation target",
            "next_action": "use_deep_acquisition",
        }
        return bundle

    try:
        result = acquire_hot_tail_via_camofox(request, db)
    except Exception as exc:
        bundle["acquisition"] = {
            **acquisition,
            "status": "hot_capture_failed",
            "reason": str(exc),
            "next_action": "use_deep_acquisition",
        }
        return bundle

    bundle["live_tail"] = result
    bundle["acquisition"] = {
        **acquisition,
        "status": "hot_captured",
        "reason": "latest rendered viewport observed without mutating the immutable snapshot",
        "next_action": "use_deep_acquisition_for_sealed_snapshot" if result["delta"]["anchored"] else "deep_acquisition_for_reconciliation",
    }
    if bundle.get("continuation") is not None:
        continuation = dict(bundle["continuation"])
        continuation["live_observation"] = True
        continuation["live_delta_anchored"] = bool(result["delta"]["anchored"])
        continuation["live_delta_count"] = len(result["delta"]["messages"])
        continuation["status"] = "resolved_live_observation"
        bundle["continuation"] = continuation
    bundle["packet"] = bundle.get("packet", "") + _live_observation_packet(result)
    return bundle


def _live_observation_packet(result: dict[str, Any]) -> str:
    delta = result.get("delta") or {}
    lines = [
        "",
        "LIVE OBSERVATION — UNSEALED",
        "This is a recent browser observation, not an immutable promoted snapshot.",
        f"observation_id={((result.get('observation') or {}).get('observation_id'))}",
        f"observed_at={((result.get('observation') or {}).get('observed_at'))}",
        f"anchored_to_current={bool(delta.get('anchored'))}",
        f"overlap_messages={delta.get('overlap_messages', 0)}",
    ]
    for item in delta.get("messages") or []:
        lines += [
            f"--- live observation {item.get('observation_index')} ---",
            f"role={item.get('role')}",
            item.get("text", ""),
            "--- END LIVE OBSERVATION ---",
        ]
    return "\n".join(lines) + "\n"


def run_context_request(
    db: ArchiveDB,
    request: ContextRequest,
    *,
    adapter: AcquisitionAdapter | None = None,
    max_attempts: int = 1,
) -> dict[str, Any]:
    if max_attempts < 0:
        raise ValueError("max_attempts must be >= 0")

    bundle = context_request(db, request)
    acquisition = bundle.get("acquisition") or {}
    if acquisition.get("status") != "acquisition_required":
        return bundle
    if not request.freshness.allow_live_acquisition:
        return bundle

    if adapter is None:
        bundle["acquisition"] = {
            **acquisition,
            "status": "acquisition_unavailable",
            "reason": "live acquisition was requested but no adapter is registered",
            "next_action": None,
        }
        return bundle

    last_error: str | None = None
    for attempt in range(max_attempts):
        try:
            result = adapter(request, db)
            bundle = context_request(db, request)
            if isinstance(result, dict) and result.get("observation_complete") is False:
                bundle["acquisition"] = {
                    **(bundle.get("acquisition") or {}),
                    "status": "partial_not_promoted",
                    "attempt": attempt + 1,
                    "result": result,
                    "next_action": "acquire_again_or_accept_stale",
                }
            else:
                bundle["acquisition"] = {
                    **(bundle.get("acquisition") or {}),
                    "status": "acquired_and_retried",
                    "attempt": attempt + 1,
                    "result": result,
                    "next_action": None,
                }
            return bundle
        except Exception as exc:  # adapter boundary: failure is data, not a crash
            last_error = str(exc)

    bundle["acquisition"] = {
        **acquisition,
        "status": "acquisition_failed",
        "reason": last_error or "acquisition failed",
        "next_action": None,
        "attempts": max_attempts,
    }
    return bundle
