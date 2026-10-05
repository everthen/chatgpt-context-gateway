from pathlib import Path

from context_gateway.camofox import (
    BrowserTurn,
    CamofoxObservation,
    collect_conversation,
    conversation_id_from_url,
    parse_visible_turns,
)


SNAPSHOT_ONE = """- heading "You said:" [level=4]
  - text: first user turn
- heading "ChatGPT said:" [level=4]
  - paragraph:
    - text: first assistant turn
- heading "You said:" [level=4]
  - text: second user turn
"""


SNAPSHOT_TWO = """- heading "You said:" [level=4]
  - text: older user turn
- heading "ChatGPT said:" [level=4]
  - paragraph:
    - text: older assistant turn
- heading "You said:" [level=4]
  - text: first user turn
- heading "ChatGPT said:" [level=4]
  - paragraph:
    - text: first assistant turn
"""


class FakeCamofoxClient:
    def __init__(self):
        self.index = 0
        self.snapshots = [
            {"snapshot": SNAPSHOT_ONE},
            {"snapshot": SNAPSHOT_TWO},
            {"snapshot": SNAPSHOT_TWO},
        ]

    def get_tab(self, user_id, tab_id):
        return {
            "tabId": tab_id,
            "url": "https://chatgpt.com/c/conv-123?src=history_search",
            "title": "Engineering Loop",
        }

    def snapshot(self, user_id, tab_id):
        item = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        return item

    def scroll_metrics(self, user_id, tab_id):
        # First pass is not at the top; subsequent pass is at the top.
        return {"scrollTop": 1000 if self.index == 0 else 0}

    def scroll_up(self, user_id, tab_id, amount=1800):
        self.index += 1
        return {"ok": True}


def test_conversation_id_from_url():
    assert conversation_id_from_url("https://chatgpt.com/c/abc-123?src=history_search") == "abc-123"


def test_parse_visible_turns():
    turns = parse_visible_turns(SNAPSHOT_ONE)
    assert [turn.role for turn in turns] == ["user", "assistant", "user"]
    assert [turn.text for turn in turns] == [
        "first user turn",
        "first assistant turn",
        "second user turn",
    ]


def test_observation_payload_preserves_browser_provenance():
    observation = CamofoxObservation(
        provider="chatgpt",
        account_id="main",
        conversation_id="conv-123",
        title="Engineering Loop",
        url="https://chatgpt.com/c/conv-123",
        turns=(
            BrowserTurn("user", "one", 0),
            BrowserTurn("assistant", "two", 1),
        ),
        snapshot_hashes=("hash1", "hash2"),
        raw_snapshots=("snapshot-1", "snapshot-2"),
        scroll_rounds=2,
        complete=True,
        captured_at=1700000000,
    )
    payload = observation.to_payload()
    assert payload["id"] == "conv-123"
    assert payload["_gateway_observation"]["source"] == "camofox-browser"
    assert payload["_gateway_observation"]["complete"] is True
    assert payload["mapping"][payload["current_node"]]["message"]["author"]["role"] == "assistant"


def test_collect_conversation_scrolls_and_proves_top(tmp_path: Path):
    client = FakeCamofoxClient()
    observation = collect_conversation(
        client,
        user_id="u1",
        tab_id="t1",
        account_id="main",
        settle_seconds=0,
        max_scrolls=5,
    )

    assert observation.conversation_id == "conv-123"
    assert observation.complete is True
    assert len(observation.snapshot_hashes) >= 2
    assert [turn.text for turn in observation.turns] == [
        "older user turn",
        "older assistant turn",
        "first user turn",
        "first assistant turn",
        "second user turn",
    ]
