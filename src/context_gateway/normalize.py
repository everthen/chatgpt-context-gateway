import hashlib
import json
from typing import Any

def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()

def extract_text(conv: dict[str, Any]) -> str:
    mapping = conv.get("mapping") or {}
    current = conv.get("current_node")
    if not current and mapping:
        leaves = [n for n in mapping.values() if not n.get("children")]
        current = leaves[-1].get("id") if leaves else None
    seen = set()
    chain = []
    while current and current not in seen:
        seen.add(current)
        node = mapping.get(current)
        if not node:
            break
        chain.append(node)
        current = node.get("parent")
    out = []
    for node in reversed(chain):
        msg = node.get("message") or {}
        role = (msg.get("author") or {}).get("role")
        content = msg.get("content") or {}
        if role not in ("user", "assistant", "tool"):
            continue
        if content.get("content_type") in ("thoughts", "reasoning_recap"):
            continue
        parts = content.get("parts") or []
        text = "\n".join(p if isinstance(p, str) else str(p) for p in parts)
        if text.strip():
            out.append(f"{role}:\n{text}")
    return "\n\n".join(out)

def make_record(conv, project_id, project_name, raw_path, provider="chatgpt", account_id="default", source=None):
    provider = provider or "chatgpt"
    return {
        "id": conv.get("id") or conv.get("conversation_id"),
        "project_id": project_id,
        "project_name": project_name or "",
        "title": conv.get("title") or "Untitled",
        "create_time": conv.get("create_time"),
        "update_time": conv.get("update_time"),
        "raw_path": raw_path,
        "raw_hash": stable_hash(conv),
        "indexed_text": extract_text(conv),
        "raw_json": json.dumps(conv, ensure_ascii=False),
        "provider": provider,
        "account_id": account_id or "default",
        "source": source or provider,
    }
