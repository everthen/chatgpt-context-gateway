import os
from pathlib import Path
from typing import Any
import requests

DEFAULT_BASE_URL = "https://chatgpt.com/backend-api"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

class ChatGPTClientError(Exception):
    """Base exception for ChatGPT client errors."""
    pass

class AuthenticationError(ChatGPTClientError):
    """Raised when authentication credentials are missing or invalid."""
    pass

class NotFoundError(ChatGPTClientError):
    """Raised when a requested resource is not found (404)."""
    pass

class RateLimitError(ChatGPTClientError):
    """Raised when request rate limits are hit (429)."""
    pass

def load_env_file(path: str | Path | None = None) -> dict[str, str]:
    target_path: Path | None = None
    if path:
        p = Path(path).expanduser()
        if p.is_file():
            target_path = p
    else:
        env_from_os = os.environ.get("CHATGPT_ENV_FILE")
        if env_from_os:
            p = Path(env_from_os).expanduser()
            if p.is_file():
                target_path = p
        else:
            candidates = [
                Path.home() / ".config" / "chatgpt-context-gateway" / "env",
                Path.home() / ".chatgpt-context.env",
                Path(".env"),
            ]
            for cand in candidates:
                if cand.is_file():
                    target_path = cand
                    break

    if not target_path or not target_path.is_file():
        return {}

    env_vars: dict[str, str] = {}
    with open(target_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            env_vars[k] = v
    return env_vars

class ChatGPTClient:
    def __init__(
        self,
        access_token: str | None = None,
        cookie: str | None = None,
        base_url: str | None = None,
        user_agent: str | None = None,
        env_file: str | Path | None = None,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        file_env = load_env_file(env_file)

        self.access_token = (
            access_token
            or file_env.get("CHATGPT_ACCESS_TOKEN")
            or file_env.get("CHATGPT_TOKEN")
            or file_env.get("OPENAI_ACCESS_TOKEN")
            or os.environ.get("CHATGPT_ACCESS_TOKEN")
            or os.environ.get("CHATGPT_TOKEN")
            or os.environ.get("OPENAI_ACCESS_TOKEN")
        )

        self.cookie = (
            cookie
            or file_env.get("CHATGPT_COOKIE")
            or file_env.get("CHATGPT_COOKIES")
            or file_env.get("COOKIE")
            or os.environ.get("CHATGPT_COOKIE")
            or os.environ.get("CHATGPT_COOKIES")
            or os.environ.get("COOKIE")
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
                "No ChatGPT credentials found. Set CHATGPT_ACCESS_TOKEN or CHATGPT_COOKIE "
                "in an external env file (e.g. ~/.config/chatgpt-context-gateway/env) "
                "or via environment variables."
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
        if self.cookie:
            headers["Cookie"] = self.cookie

        self.session.headers.update(headers)

    def __repr__(self) -> str:
        has_token = bool(self.access_token)
        has_cookie = bool(self.cookie)
        return f"<ChatGPTClient base_url={self.base_url!r} has_token={has_token} has_cookie={has_cookie}>"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)

        resp = self.session.request(method, url, **kwargs)

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"ChatGPT authentication failed (HTTP {resp.status_code}): session may have expired."
            )
        elif resp.status_code == 404:
            raise NotFoundError(f"Resource not found (HTTP 404) at {url}")
        elif resp.status_code == 429:
            raise RateLimitError("ChatGPT rate limit exceeded (HTTP 429).")
        elif not resp.ok:
            raise ChatGPTClientError(
                f"ChatGPT request failed (HTTP {resp.status_code}): {resp.text[:200]}"
            )

        return resp.json()

    def list_projects(self) -> list[dict[str, Any]]:
        try:
            data = self._request("GET", "projects")
        except NotFoundError:
            try:
                data = self._request("GET", "gizmos/projects")
            except NotFoundError:
                data = self._request("GET", "workspace/projects")

        raw_items: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict):
            raw_items = data.get("items") or data.get("projects") or data.get("data") or []

        projects = []
        for item in raw_items:
            projects.append({
                "id": str(item.get("id", "")),
                "name": item.get("name") or item.get("title") or item.get("id") or "Untitled Project",
                "created_at": item.get("created_at") or item.get("create_time"),
                "updated_at": item.get("updated_at") or item.get("update_time"),
                "raw": item,
            })
        return projects

    def list_conversations(
        self,
        project_id: str | None = None,
        offset: int = 0,
        limit: int = 28,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if project_id:
            try:
                data = self._request("GET", f"projects/{project_id}/conversations", params=params)
            except NotFoundError:
                params["project_id"] = project_id
                data = self._request("GET", "conversations", params=params)
        else:
            params["order"] = "updated"
            data = self._request("GET", "conversations", params=params)

        if isinstance(data, list):
            return {"items": data, "total": len(data), "offset": offset, "limit": limit}

        items = data.get("items") or data.get("conversations") or []
        total = data.get("total")
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"conversation/{conversation_id}")
