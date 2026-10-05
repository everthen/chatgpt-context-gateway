import os
from pathlib import Path
from typing import Any
import requests

DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

class ChatGPTClientError(Exception):
    pass

class AuthenticationError(ChatGPTClientError):
    pass

class NotFoundError(ChatGPTClientError):
    pass

class RateLimitError(ChatGPTClientError):
    pass

def load_env_file(path: str | Path | None = None) -> dict[str, str]:
    candidates = []
    if path:
        candidates.append(Path(path).expanduser())
    elif os.environ.get("CHATGPT_ENV_FILE"):
        candidates.append(Path(os.environ["CHATGPT_ENV_FILE"]).expanduser())
    else:
        candidates.extend([
            Path.home() / ".config/chatgpt-context-gateway/env",
            Path.home() / ".chatgpt-context.env",
            Path(".env"),
        ])

    target = next((p for p in candidates if p.is_file()), None)
    if target is None:
        return {}

    values: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values

class ChatGPTClient:
    def __init__(
        self,
        access_token: str | None = None,
        cookie: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        user_agent: str | None = None,
        env_file: str | Path | None = None,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        file_env = load_env_file(env_file)
        self.access_token = (
            access_token
            or file_env.get("OAI_AUTHZ_TOKEN")
            or file_env.get("CHATGPT_ACCESS_TOKEN")
            or file_env.get("CHATGPT_TOKEN")
            or os.environ.get("OAI_AUTHZ_TOKEN")
            or os.environ.get("CHATGPT_ACCESS_TOKEN")
            or os.environ.get("CHATGPT_TOKEN")
        )
        self.account_id = (
            account_id
            or file_env.get("OAI_ACC_ID")
            or file_env.get("CHATGPT_ACCOUNT_ID")
            or os.environ.get("OAI_ACC_ID")
            or os.environ.get("CHATGPT_ACCOUNT_ID")
        )
        self.cookie = (
            cookie
            or file_env.get("OAI_COOKIE")
            or file_env.get("CHATGPT_COOKIE")
            or file_env.get("CHATGPT_COOKIES")
            or os.environ.get("OAI_COOKIE")
            or os.environ.get("CHATGPT_COOKIE")
            or os.environ.get("CHATGPT_COOKIES")
        )
        self.base_url = (
            base_url
            or file_env.get("CHATGPT_BASE_URL")
            or os.environ.get("CHATGPT_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.user_agent = (
            user_agent
            or file_env.get("CHATGPT_USER_AGENT")
            or os.environ.get("CHATGPT_USER_AGENT")
            or DEFAULT_USER_AGENT
        )
        self.timeout = timeout
        if not self.access_token and not self.cookie:
            raise AuthenticationError(
                "No ChatGPT credentials found. Set OAI_AUTHZ_TOKEN/OAI_COOKIE "
                "or CHATGPT_ACCESS_TOKEN/CHATGPT_COOKIE in an external env file."
            )

        self.session = session or requests.Session()
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "oai-language": "en-US",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
            headers["x-authorization"] = f"Bearer {self.access_token}"
        if self.account_id:
            headers["chatgpt-account-id"] = self.account_id
        if self.cookie:
            headers["Cookie"] = self.cookie
        self.session.headers.update(headers)

    def __repr__(self) -> str:
        return (
            f"<ChatGPTClient base_url={self.base_url!r} "
            f"has_token={bool(self.access_token)} "
            f"has_account_id={bool(self.account_id)} "
            f"has_cookie={bool(self.cookie)}>"
        )

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.request(method, url, **kwargs)
        if resp.status_code in (401, 403):
            raise AuthenticationError(f"ChatGPT authentication failed (HTTP {resp.status_code}).")
        if resp.status_code == 404:
            raise NotFoundError(f"Resource not found: {path}")
        if resp.status_code == 429:
            raise RateLimitError("ChatGPT rate limit exceeded (HTTP 429).")
        if not resp.ok:
            raise ChatGPTClientError(f"ChatGPT request failed (HTTP {resp.status_code}).")
        return resp.json()

    @staticmethod
    def _normalize_project(item: dict[str, Any]) -> dict[str, Any]:
        outer = item.get("gizmo") or {}
        gizmo = outer.get("gizmo") if isinstance(outer, dict) else None
        if not isinstance(gizmo, dict):
            gizmo = outer if isinstance(outer, dict) else item
        display = gizmo.get("display") or {}
        return {
            "id": str(gizmo.get("id") or item.get("id") or ""),
            "name": display.get("name") or gizmo.get("name") or item.get("name") or "Untitled Project",
            "created_at": gizmo.get("created_at") or item.get("created_at"),
            "updated_at": gizmo.get("updated_at") or item.get("updated_at"),
            "raw": item,
        }

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        cursor = None
        while True:
            params = {"conversations_per_gizmo": 0}
            if cursor:
                params["cursor"] = cursor
            try:
                data = self._request("GET", "gizmos/snorlax/sidebar", params=params)
            except NotFoundError:
                data = self._request("GET", "projects")
                items = data if isinstance(data, list) else (data.get("items") or data.get("projects") or [])
                return [self._normalize_project(x) for x in items]

            projects.extend(self._normalize_project(x) for x in (data.get("items") or []))
            cursor = data.get("cursor")
            if not cursor:
                return projects

    def list_conversations(
        self,
        project_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        if not project_id:
            data = self._request("GET", "conversations", params={"offset": offset, "limit": limit, "order": "updated"})
            items = data if isinstance(data, list) else (data.get("items") or data.get("conversations") or [])
            return {"items": items, "total": data.get("total") if isinstance(data, dict) else len(items), "offset": offset, "limit": limit}

        items: list[dict[str, Any]] = []
        cursor = None
        while True:
            params = {"gizmo": project_id, "limit": str(limit)}
            if cursor:
                params["cursor"] = cursor
            try:
                data = self._request("GET", f"gizmos/{project_id}/conversations", params=params)
            except NotFoundError:
                params2 = {"project_id": project_id, "offset": offset + len(items), "limit": limit}
                data = self._request("GET", "conversations", params=params2)
                page = data if isinstance(data, list) else (data.get("items") or data.get("conversations") or [])
                items.extend(page)
                total = data.get("total") if isinstance(data, dict) else len(items)
                return {"items": items, "total": total, "offset": offset, "limit": limit}

            page = data.get("items") or []
            items.extend(page)
            cursor = data.get("cursor")
            if not cursor:
                return {"items": items, "total": len(items), "offset": offset, "limit": limit}

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"conversation/{conversation_id}")
