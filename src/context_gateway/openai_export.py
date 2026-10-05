from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .config import get_raw_dir, safe_project_name
from .db import ArchiveDB
from .normalize import make_record

class OpenAIExportError(Exception):
    pass

def _iter_json_documents(path: Path) -> Iterable[tuple[str, Any]]:
    if path.is_dir():
        for item in sorted(path.rglob("*.json")):
            yield from _iter_json_documents(item)
        return
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".json") and not n.endswith("/")]
            for name in sorted(names):
                try:
                    yield name, json.loads(zf.read(name).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise OpenAIExportError(f"invalid JSON in export member: {name}") from exc
        return
    if path.suffix.lower() != ".json":
        raise OpenAIExportError("input must be a JSON file, directory, or ZIP export")
    try:
        yield path.name, json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenAIExportError(f"invalid JSON file: {path}") from exc

def _conversation_items(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        return [x for x in document if isinstance(x, dict) and (x.get("id") or x.get("conversation_id"))]
    if isinstance(document, dict):
        candidates = document.get("conversations")
        if isinstance(candidates, list):
            return [x for x in candidates if isinstance(x, dict) and (x.get("id") or x.get("conversation_id"))]
        if document.get("id") or document.get("conversation_id"):
            return [document]
    return []

def _project_fields(conv: dict[str, Any]) -> tuple[str, str]:
    gizmo = conv.get("gizmo")
    gizmo = gizmo if isinstance(gizmo, dict) else {}
    project_id = conv.get("project_id") or conv.get("gizmo_id") or gizmo.get("id")
    project_name = conv.get("project_name") or conv.get("gizmo_name") or gizmo.get("name")
    return str(project_id or "imported-openai"), str(project_name or "Imported / OpenAI")

def import_openai_export(
    source: str | Path,
    account_id: str,
    db: ArchiveDB,
    raw_dir: Path | None = None,
) -> dict[str, int]:
    source = Path(source).expanduser()
    if not source.exists():
        raise OpenAIExportError(f"export not found: {source}")

    account_id = safe_project_name(account_id)
    raw_dir = Path(raw_dir or get_raw_dir())
    counts: dict[str, int] = {}
    seen: set[str] = set()

    for _, document in _iter_json_documents(source):
        for conv in _conversation_items(document):
            cid = str(conv.get("id") or conv.get("conversation_id"))
            if cid in seen:
                continue
            seen.add(cid)

            project_id, project_name = _project_fields(conv)
            project_key = safe_project_name(project_name)
            project = {
                "id": project_id,
                "name": project_name,
                "created_at": conv.get("create_time"),
                "updated_at": conv.get("update_time"),
                "provider": "openai",
                "account_id": account_id,
                "source": "openai-export",
            }
            db.upsert_project(project)

            out_dir = raw_dir / "openai" / account_id / project_key
            out_dir.mkdir(parents=True, exist_ok=True)
            raw_path = out_dir / f"{cid}.json"
            raw_path.write_text(json.dumps(conv, ensure_ascii=False, indent=2), encoding="utf-8")

            record = make_record(
                conv,
                project_id=project_id,
                project_name=project_name,
                raw_path=str(raw_path),
                provider="openai",
                account_id=account_id,
                source="openai-export",
            )
            db.upsert_conversation(record)
            counts[project_name] = counts.get(project_name, 0) + 1

    return counts
