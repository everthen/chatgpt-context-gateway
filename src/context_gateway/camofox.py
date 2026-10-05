from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from .normalize import stable_hash


_MESSAGE_HEADING = re.compile(r'^\s*-\s*heading "(You said:|ChatGPT said:)"')
_CONTENT_TAGS = {
    "text",
    "paragraph",
    "code",
    "blockquote",
    "strong",
    "emphasis",
    "heading",
    "listitem",
    "row",
    "cell",
    "link",
}
_CONVERSATION_ID = re.compile(r"/c/([^/?#]+)")


@dataclass(frozen=True)
class BrowserTurn:
    role: str
    text: str
    observation_index: int


@dataclass(frozen=True)
class CamofoxObservation:
    provider: str
    account_id: str
    conversation_id: str
    title: str
    url: str
    turns: tuple[BrowserTurn, ...]
    snapshot_hashes: tuple[str, ...]
    raw_snapshots: tuple[str, ...]
    scroll_rounds: int
    complete: bool
    captured_at: float

    def to_payload(self) -> dict[str, Any]:
        mapping: dict[str, dict[str, Any]] = {}
        previous_node: str | None = None

        for ordinal, turn in enumerate(self.turns):
            digest = hashlib.sha256(
                f"{self.conversation_id}\0{turn.role}\0{turn.text}\0{ordinal}".encode()
            ).hexdigest()[:24]
            node_id = f"camofox-node-{digest}"
            message_id = f"camofox-message-{digest}"
            mapping[node_id] = {
                "id": node_id,
                "parent": previous_node,
                "children": [],
                "message": {
                    "id": message_id,
                    "author": {"role": turn.role},
                    "content": {"content_type": "text", "parts": [turn.text]},
                    "create_time": None,
                },
            }
            if previous_node:
                mapping[previous_node]["children"] = [node_id]
            previous_node = node_id

        return {
            "id": self.conversation_id,
            "title": self.title or "Untitled",
            "create_time": self.captured_at,
            "update_time": self.captured_at,
            "mapping": mapping,
            "current_node": previous_node,
            "_gateway_observation": {
                "source": "camofox-browser",
                "account_id": self.account_id,
                "captured_at": self.captured_at,
                "url": self.url,
                "complete": self.complete,
                "scroll_rounds": self.scroll_rounds,
                "turn_count": len(self.turns),
                "snapshot_hashes": list(self.snapshot_hashes),
                "raw_snapshots": list(self.raw_snapshots),
            },
        }


class CamofoxClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:9377",
        *,
        session: requests.Session | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            **kwargs,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Camofox response must be an object")
        return data

    def list_tabs(self, user_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", "/tabs", params={"userId": user_id})
        tabs = data.get("tabs") or []
        return [tab for tab in tabs if isinstance(tab, dict)]

    def get_tab(self, user_id: str, tab_id: str) -> dict[str, Any]:
        for tab in self.list_tabs(user_id):
            if tab.get("tabId") == tab_id:
                return tab
        raise ValueError(f"Camofox tab '{tab_id}' not found for user '{user_id}'")

    def snapshot(self, user_id: str, tab_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/tabs/{tab_id}/snapshot",
            params={"userId": user_id, "format": "text"},
        )

    def scroll_up(self, user_id: str, tab_id: str, amount: int = 1800) -> dict[str, Any]:
        try:
            return self._request(
                "POST",
                f"/tabs/{tab_id}/scroll",
                json={"userId": user_id, "direction": "up", "amount": int(amount)},
            )
        except requests.HTTPError:
            expression = (
                "(()=>{"
                "const es=[...document.querySelectorAll('*')]"
                ".filter(e=>e.scrollHeight>e.clientHeight+100)"
                ".sort((a,b)=>b.scrollHeight-a.scrollHeight);"
                "const e=es[0]||document.scrollingElement;"
                f"const before=e.scrollTop;e.scrollTop=Math.max(0,before-{int(amount)});"
                "return {before,after:e.scrollTop,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight};"
                "})()"
            )
            return self._request(
                "POST",
                f"/tabs/{tab_id}/evaluate",
                json={"userId": user_id, "expression": expression},
            )

    def scroll_metrics(self, user_id: str, tab_id: str) -> dict[str, Any]:
        expression = (
            "(()=>{"
            "const es=[...document.querySelectorAll('*')]"
            ".filter(e=>e.scrollHeight>e.clientHeight+100)"
            ".sort((a,b)=>b.scrollHeight-a.scrollHeight);"
            "const e=es[0]||document.scrollingElement;"
            "return {scrollTop:e.scrollTop,scrollHeight:e.scrollHeight,clientHeight:e.clientHeight};"
            "})()"
        )
        data = self._request(
            "POST",
            f"/tabs/{tab_id}/evaluate",
            json={"userId": user_id, "expression": expression},
        )
        result = data.get("result")
        return result if isinstance(result, dict) else {}


def conversation_id_from_url(url: str) -> str:
    match = _CONVERSATION_ID.search(url)
    if not match:
        raise ValueError(f"cannot identify ChatGPT conversation id from URL: {url}")
    return match.group(1)


def _strip_heading_metadata(value: str) -> str:
    match = re.match(r'^"([^"]*)"', value.strip())
    return match.group(1) if match else value.strip()


def parse_visible_turns(snapshot: str) -> list[BrowserTurn]:
    turns: list[BrowserTurn] = []
    current_role: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_role, current_parts
        if current_role is None:
            return
        text = "\n".join(p.strip() for p in current_parts if p.strip()).strip()
        if text:
            turns.append(
                BrowserTurn(
                    role=current_role,
                    text=text,
                    observation_index=len(turns),
                )
            )
        current_role = None
        current_parts = []

    for line in snapshot.splitlines():
        match = _MESSAGE_HEADING.match(line)
        if match:
            flush()
            current_role = "user" if match.group(1) == "You said:" else "assistant"
            continue

        if current_role is None:
            continue

        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:]
        if ":" not in body:
            continue
        tag, value = body.split(":", 1)
        tag = tag.strip()
        value = value.strip()
        if tag not in _CONTENT_TAGS:
            continue
        if tag == "heading":
            value = _strip_heading_metadata(value)
        if value and not value.startswith("Worked for "):
            current_parts.append(value)

    flush()
    return turns


def _turn_key(turn: BrowserTurn) -> str:
    return stable_hash({"role": turn.role, "text": turn.text})


def collect_conversation(
    client: CamofoxClient,
    *,
    user_id: str,
    tab_id: str,
    account_id: str,
    max_scrolls: int = 60,
    scroll_amount: int = 1800,
    settle_seconds: float = 0.25,
) -> CamofoxObservation:
    tab = client.get_tab(user_id, tab_id)
    url = str(tab.get("url") or "")
    conversation_id = conversation_id_from_url(url)
    title = str(tab.get("title") or "Untitled")

    ordered: list[BrowserTurn] = []
    snapshot_hashes: list[str] = []
    raw_snapshots: list[str] = []
    previous_frontier: tuple[tuple[str, str], ...] | None = None
    no_new_frontier_rounds = 0
    complete = False
    rounds = 0

    def turn_signature(turn: BrowserTurn) -> tuple[str, str]:
        return turn.role, turn.text

    def merge_scrolled_window(existing: list[BrowserTurn], visible: list[BrowserTurn]) -> list[BrowserTurn]:
        if not existing:
            return list(visible)
        if not visible:
            return existing

        existing_sig = [turn_signature(turn) for turn in existing]
        visible_sig = [turn_signature(turn) for turn in visible]
        max_overlap = min(len(existing_sig), len(visible_sig))
        for overlap in range(max_overlap, 0, -1):
            if visible_sig[-overlap:] == existing_sig[:overlap]:
                return visible + existing[overlap:]
        return visible + existing

    for round_index in range(max_scrolls + 1):
        rounds = round_index
        snapshot = client.snapshot(user_id, tab_id)
        text = str(snapshot.get("snapshot") or "")
        snapshot_hashes.append(stable_hash(text))
        raw_snapshots.append(text)

        visible = parse_visible_turns(text)
        ordered = merge_scrolled_window(ordered, visible)
        frontier = tuple(turn_signature(turn) for turn in visible[:3])
        if frontier and frontier == previous_frontier:
            no_new_frontier_rounds += 1
        else:
            no_new_frontier_rounds = 0
        previous_frontier = frontier

        metrics = client.scroll_metrics(user_id, tab_id)
        if float(metrics.get("scrollTop") or 0) <= 0:
            complete = True
            break

        if no_new_frontier_rounds >= 2:
            complete = True
            break

        if round_index >= max_scrolls:
            break

        client.scroll_up(user_id, tab_id, amount=scroll_amount)
        if settle_seconds > 0:
            time.sleep(settle_seconds)

    # Browser snapshots expose chronological viewport order. Scrolling upward adds older
    # turns before the existing window; longest exact boundary overlap preserves repeated
    # identical message occurrences instead of globally deduplicating by text.

    return CamofoxObservation(
        provider="chatgpt",
        account_id=account_id,
        conversation_id=conversation_id,
        title=title,
        url=url,
        turns=tuple(ordered),
        snapshot_hashes=tuple(snapshot_hashes),
        raw_snapshots=tuple(raw_snapshots),
        scroll_rounds=rounds,
        complete=complete,
        captured_at=time.time(),
    )
