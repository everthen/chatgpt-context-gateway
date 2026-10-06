from pathlib import Path

from context_gateway.account import account_status, begin_chatgpt_login, wait_for_chatgpt_login
from context_gateway.db import ArchiveDB


class FakeAccountCamofox:
    def __init__(self):
        self.tabs = []
        self.polls = 0

    def list_tabs(self, user_id):
        return list(self.tabs)

    def create_tab(self, user_id, session_key, url=None):
        tab = {
            "tabId": "login-tab",
            "url": url or "https://chatgpt.com/auth/login",
            "title": "Log in — ChatGPT",
        }
        self.tabs.append(tab)
        return tab


def test_begin_chatgpt_login_registers_profile_and_creates_tab(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    client = FakeAccountCamofox()

    result = begin_chatgpt_login(
        db,
        account_id="personal",
        profile_id="chatgpt_human_login",
        client=client,
    )

    assert result["status"] == "login_required"
    assert result["tab"]["tabId"] == "login-tab"
    profile = db.get_account_profile("chatgpt", "personal")
    assert profile["profile_id"] == "chatgpt_human_login"
    assert profile["status"] == "pending"


def test_wait_for_chatgpt_login_promotes_profile(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    client = FakeAccountCamofox()
    begin_chatgpt_login(db, account_id="personal", profile_id="profile-1", client=client)
    client.tabs[0].update({
        "url": "https://chatgpt.com/c/abc123",
        "title": "Test conversation",
    })

    result = wait_for_chatgpt_login(
        db,
        account_id="personal",
        timeout_seconds=1,
        poll_seconds=0,
        client=client,
    )

    assert result["status"] == "ready"
    profile = db.get_account_profile("chatgpt", "personal")
    assert profile["status"] == "ready"
    assert profile["last_verified_at"] is not None


def test_account_status_auth_required(tmp_path: Path):
    db = ArchiveDB(tmp_path / "db.sqlite3")
    client = FakeAccountCamofox()
    begin_chatgpt_login(db, account_id="personal", profile_id="profile-1", client=client)

    result = account_status(db, account_id="personal", client=client)

    assert result["status"] == "auth_required"
