from __future__ import annotations

import html
import os
import secrets
import shlex
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .client import ChatGPTClient, ChatGPTClientError

DEFAULT_ENV_PATH = Path.home() / ".config/chatgpt-context-gateway/env"
CHATGPT_HOSTS = {"chatgpt.com", "www.chatgpt.com"}


class CredentialImportError(ValueError):
    """Raised when a captured browser request cannot be safely imported."""


def parse_curl_capture(text: str) -> dict[str, str]:
    """Extract supported ChatGPT backend headers from a copied cURL request.

    The parser only accepts requests targeting chatgpt.com and never executes
    the supplied shell text.
    """
    tokens = shlex.split(text, posix=True)
    if not tokens or tokens[0] not in {"curl", "curl.exe"}:
        raise CredentialImportError("Paste a complete cURL request copied from the browser.")

    url = None
    headers: dict[str, str] = {}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in {"-H", "--header"}:
            if i + 1 >= len(tokens):
                raise CredentialImportError("Malformed cURL: header value is missing.")
            raw = tokens[i + 1]
            if ":" not in raw:
                raise CredentialImportError("Malformed cURL header.")
            key, value = raw.split(":", 1)
            headers[key.strip().lower()] = value.strip()
            i += 2
            continue
        if token in {"-b", "--cookie"}:
            if i + 1 >= len(tokens):
                raise CredentialImportError("Malformed cURL: cookie value is missing.")
            headers["cookie"] = tokens[i + 1]
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        if url is None and token.startswith(("http://", "https://")):
            url = token
        i += 1

    if not url:
        raise CredentialImportError("The copied cURL does not contain a URL.")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in CHATGPT_HOSTS:
        raise CredentialImportError("Only https://chatgpt.com requests are accepted.")

    auth = headers.get("authorization", "")
    cookie = headers.get("cookie", "")
    account_id = headers.get("chatgpt-account-id") or headers.get("x-chatgpt-account-id", "")

    if auth.lower().startswith("bearer "):
        auth_token = auth[7:].strip()
    else:
        auth_token = auth.strip()

    if not auth_token and not cookie:
        raise CredentialImportError(
            "The request contains neither Authorization nor Cookie credentials."
        )

    values = {
        "OAI_AUTHZ_TOKEN": auth_token,
        "OAI_COOKIE": cookie,
        "OAI_ACC_ID": account_id,
    }
    user_agent = headers.get("user-agent", "").strip()
    if user_agent:
        values["CHATGPT_USER_AGENT"] = user_agent
    return values


def save_credentials(values: dict[str, str], path: str | Path = DEFAULT_ENV_PATH) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Managed by chatgpt-context connect.",
        "# Keep this file local and never commit or paste its contents into chat.",
    ]
    for key in ("OAI_AUTHZ_TOKEN", "OAI_ACC_ID", "OAI_COOKIE", "CHATGPT_USER_AGENT"):
        value = values.get(key, "")
        if value:
            lines.append(f"{key}={value}")
    temp = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(target)
    os.chmod(target, 0o600)
    return target


def _page(nonce: str, message: str | None = None, error: bool = False) -> str:
    notice = ""
    if message:
        css = "error" if error else "ok"
        notice = f'<p class="{css}">{html.escape(message)}</p>'
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>ChatGPT Context Gateway — Connect</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:860px;margin:40px auto;padding:0 20px;line-height:1.5}}
code,textarea{{font-family:ui-monospace,monospace}}
textarea{{width:100%;min-height:220px}}
button{{padding:10px 18px;font-weight:600;cursor:pointer}}
.card{{padding:20px;border:1px solid #ddd;border-radius:12px;margin:16px 0}}
.ok{{color:#176b36}}.error{{color:#a11}}
</style>
</head>
<body>
<h1>Connect ChatGPT Web</h1>
<div class="card">
<p><strong>1.</strong> Log in at chatgpt.com.</p>
<p><strong>2.</strong> In the logged-in ChatGPT tab, open Developer Tools → Network.</p>
<p><strong>3.</strong> Trigger any normal ChatGPT request, select a request to
<code>/backend-api/</code>, then choose <em>Copy → Copy as cURL</em>.</p>
<p><strong>4.</strong> Paste that cURL below. The gateway parses it locally and
never executes the command.</p>
</div>
<form method="post" action="/capture">
<input type="hidden" name="nonce" value="{html.escape(nonce)}">
<textarea name="curl" placeholder="curl 'https://chatgpt.com/backend-api/...' ..."></textarea>
<br><br><button type="submit">Connect &amp; Test</button>
</form>
{notice}
</body>
</html>"""


class _ConnectHandler(BaseHTTPRequestHandler):
    server_version = "ChatGPTContextGatewayConnect/1"

    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self._send_html(_page(self.server.nonce))

    def do_POST(self) -> None:
        if self.path != "/capture":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(body)
        nonce = form.get("nonce", [""])[0]
        curl_text = form.get("curl", [""])[0]
        if not secrets.compare_digest(nonce, self.server.nonce):
            self.send_error(403)
            return

        try:
            values = parse_curl_capture(curl_text)
            path = save_credentials(values, self.server.env_path)
            client = ChatGPTClient(env_file=path)
            projects = client.list_projects()
            html_body = _page(
                self.server.nonce,
                f"Connected successfully. Found {len(projects)} project(s). Credential file: {path}",
            )
            self.server.shutdown()
        except (CredentialImportError, ChatGPTClientError, OSError) as exc:
            html_body = _page(self.server.nonce, f"Connection failed: {exc}", error=True)

        self._send_html(html_body)

    def _send_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _ConnectServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, nonce: str, env_path: Path):
        super().__init__(address, handler)
        self.nonce = nonce
        self.env_path = env_path


def run_connect(
    env_path: str | Path = DEFAULT_ENV_PATH,
    host: str = "127.0.0.1",
    port: int = 8780,
    open_browser: bool = True,
) -> int:
    """Run a one-time local credential bridge for the ChatGPT Web adapter."""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("The connect bridge must stay localhost-only.")

    nonce = secrets.token_urlsafe(24)
    env = Path(env_path).expanduser()
    server = _ConnectServer((host, port), _ConnectHandler, nonce, env)
    url = f"http://127.0.0.1:{port}/"
    print(f"ChatGPT connect bridge: {url}")
    print("This bridge is localhost-only and is intended for one-time setup.")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nConnect flow stopped.")
    finally:
        server.server_close()
    return 0
