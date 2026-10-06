from __future__ import annotations

import time
from typing import Any

from .camofox import CamofoxClient
from .config import get_camofox_profile_id
from .db import ArchiveDB

CHATGPT_LOGIN_URL = "https://chatgpt.com/auth/login"
CHATGPT_HOME_URL = "https://chatgpt.com/"


def _chatgpt_tabs(client: CamofoxClient, profile_id: str) -> list[dict[str, Any]]:
    return client.list_tabs(profile_id)


def _is_chatgpt_authenticated(tab: dict[str, Any]) -> bool:
    url = str(tab.get("url") or "")
    if not url.startswith("https://chatgpt.com/"):
        return False
    return "/auth/" not in url and "/login" not in url and "/signup" not in url


def account_status(
    db: ArchiveDB,
    *,
    provider: str = "chatgpt",
    account_id: str,
    client: CamofoxClient | None = None,
) -> dict[str, Any]:
    profile = db.get_account_profile(provider, account_id)
    if not profile:
        return {"status": "unconfigured", "provider": provider, "account_id": account_id}
    client = client or CamofoxClient()
    tabs = _chatgpt_tabs(client, profile["profile_id"]) if provider == "chatgpt" else []
    authenticated_tabs = [tab for tab in tabs if _is_chatgpt_authenticated(tab)]
    status = "ready" if authenticated_tabs else "auth_required"
    now = time.time()
    if status == "ready":
        db.upsert_account_profile({
            **profile,
            "status": "ready",
            "last_verified_at": now,
            "last_seen_at": now,
            "metadata": {**(profile.get("metadata") or {}), "authenticated_tab_count": len(authenticated_tabs)},
        })
    return {
        "status": status,
        "provider": provider,
        "account_id": account_id,
        "profile_id": profile["profile_id"],
        "authenticated_tabs": len(authenticated_tabs),
        "tabs": len(tabs),
        "last_verified_at": profile.get("last_verified_at"),
    }


def begin_chatgpt_login(
    db: ArchiveDB,
    *,
    account_id: str,
    profile_id: str | None = None,
    client: CamofoxClient | None = None,
) -> dict[str, Any]:
    profile_id = profile_id or get_camofox_profile_id()
    client = client or CamofoxClient()
    db.upsert_account_profile({
        "provider": "chatgpt",
        "account_id": account_id,
        "profile_id": profile_id,
        "status": "pending",
        "metadata": {"login_url": CHATGPT_LOGIN_URL},
    })

    tabs = _chatgpt_tabs(client, profile_id)
    ready = next((tab for tab in tabs if _is_chatgpt_authenticated(tab)), None)
    if ready:
        db.upsert_account_profile({
            "provider": "chatgpt",
            "account_id": account_id,
            "profile_id": profile_id,
            "status": "ready",
            "last_verified_at": time.time(),
            "last_seen_at": time.time(),
            "metadata": {"login_url": CHATGPT_HOME_URL, "tab_id": ready.get("tabId")},
        })
        return {"status": "ready", "tab": ready, "profile_id": profile_id, "account_id": account_id}

    existing = next(
        (
            tab for tab in tabs
            if "/auth/login" in str(tab.get("url") or "")
            or str(tab.get("url") or "") == CHATGPT_HOME_URL
        ),
        None,
    )
    if existing:
        return {"status": "login_required", "tab": existing, "profile_id": profile_id, "account_id": account_id}

    tab = client.create_tab(
        user_id=profile_id,
        session_key=f"ucg-account-{account_id}",
        url=CHATGPT_LOGIN_URL,
    )
    return {"status": "login_required", "tab": tab, "profile_id": profile_id, "account_id": account_id}


def wait_for_chatgpt_login(
    db: ArchiveDB,
    *,
    account_id: str,
    timeout_seconds: int = 180,
    poll_seconds: float = 2.0,
    client: CamofoxClient | None = None,
) -> dict[str, Any]:
    profile = db.get_account_profile("chatgpt", account_id)
    if not profile:
        raise ValueError(f"account is not configured: {account_id}")
    client = client or CamofoxClient()
    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        tabs = _chatgpt_tabs(client, profile["profile_id"])
        ready = next((tab for tab in tabs if _is_chatgpt_authenticated(tab)), None)
        if ready:
            now = time.time()
            updated = db.upsert_account_profile({
                **profile,
                "status": "ready",
                "last_verified_at": now,
                "last_seen_at": now,
                "metadata": {**(profile.get("metadata") or {}), "tab_id": ready.get("tabId")},
            })
            return {"status": "ready", "profile": updated, "tab": ready}
        time.sleep(max(0.2, poll_seconds))
    now = time.time()
    updated = db.upsert_account_profile({**profile, "status": "auth_required", "last_seen_at": now})
    return {"status": "auth_required", "profile": updated}
