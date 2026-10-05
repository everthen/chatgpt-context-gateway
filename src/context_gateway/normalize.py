import hashlib
import json
from typing import Any


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    if content.get("content_type") in ("thoughts", "reasoning_recap"):
        return ""
    parts = content.get("parts") or []
    text = "\n".join(p if isinstance(p, str) else str(p) for p in parts)
    return text.strip()


def extract_messages(conv: dict[str, Any]) -> list[dict[str, Any]]:
    mapping = conv.get("mapping") or {}
    current = conv.get("current_node")

    if not current and mapping:
        leaves = [node for node in mapping.values() if not node.get("children")]
        current = leaves[-1].get("id") if leaves else None

    seen: set[str] = set()
    chain: list[dict[str, Any]] = []
    while current and current not in seen:
        seen.add(current)
        node = mapping.get(current)
        if not node:
            break
        chain.append(node)
        current = node.get("parent")

    ordered_nodes = list(reversed(chain))
    node_message_ids = {
        str(node.get("id")): str(
            (node.get("message") or {}).get("id") or node.get("id")
        )
        for node in ordered_nodes
        if node.get("id")
    }

    messages: list[dict[str, Any]] = []
    for ordinal, node in enumerate(ordered_nodes):
        msg = node.get("message") or {}
        role = (msg.get("author") or {}).get("role")
        if role not in ("user", "assistant", "tool"):
            continue

        text = _message_text(msg)
        if not text:
            continue

        provider_message_id = str(msg.get("id") or node.get("id") or f"node-{ordinal}")
        parent_node_id = msg.get("parent_id") or node.get("parent")
        parent_message_id = node_message_ids.get(str(parent_node_id)) if parent_node_id else None
        create_time = msg.get("create_time") or node.get("create_time")

        messages.append(
            {
                "provider_message_id": provider_message_id,
                "role": role,
                "text": text,
                "ordinal": len(messages),
                "parent_message_id": str(parent_message_id) if parent_message_id else None,
                "create_time": create_time,
            }
        )

    return messages


def messages_from_indexed_text(indexed_text: str) -> list[dict[str, Any]]:
    if not indexed_text.strip():
        return []

    chunks = [chunk.strip() for chunk in indexed_text.split("\n\n") if chunk.strip()]
    messages: list[dict[str, Any]] = []
    for chunk in chunks:
        if ":\n" in chunk:
            role, text = chunk.split(":\n", 1)
        else:
            role, text = "unknown", chunk
        messages.append(
            {
                "provider_message_id": f"legacy-{len(messages)}",
                "role": role,
                "text": text.strip(),
                "ordinal": len(messages),
                "parent_message_id": messages[-1]["provider_message_id"] if messages else None,
                "create_time": None,
            }
        )
    return [item for item in messages if item["text"]]


def extract_text(conv: dict[str, Any]) -> str:
    return "\n\n".join(
        f"{item['role']}:\n{item['text']}" for item in extract_messages(conv)
    )


def make_record(
    conv: dict[str, Any],
    project_id: str,
    project_name: str,
    raw_path: str,
    provider: str = "chatgpt",
    account_id: str = "default",
    source: str | None = None,
    captured_at: float | None = None,
) -> dict[str, Any]:
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
        "messages": extract_messages(conv),
        "raw_json": json.dumps(conv, ensure_ascii=False),
        "provider": provider,
        "account_id": account_id or "default",
        "source": source or provider,
        "captured_at": captured_at,
    }
