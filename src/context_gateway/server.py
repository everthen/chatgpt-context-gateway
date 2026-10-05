import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .acquisition import acquire_current_conversation_via_camofox, ingest_conversation_payload, run_context_request
from .config import get_db_path, get_raw_dir
from .contracts import ContextRequest
from .continuity import (compare, context_request, context_request as resolve_context_request, continuity, project_context, timeline)
from .db import ArchiveDB


class GatewayRequestHandler(BaseHTTPRequestHandler):
    db: ArchiveDB
    raw_dir: Path

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _is_localhost(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1", "localhost", "testclient")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, error_code: str, message: str) -> None:
        self._send_json(status, {"error": error_code, "message": message})

    @staticmethod
    def _limit(query: dict[str, list[str]], default: int = 8, maximum: int = 50) -> int:
        try:
            value = int(query.get("limit", [str(default)])[0])
        except (TypeError, ValueError):
            raise ValueError("limit must be an integer")
        if value < 1 or value > maximum:
            raise ValueError(f"limit must be between 1 and {maximum}")
        return value

    @staticmethod
    def _param(query: dict[str, list[str]], name: str, maximum: int, required: bool = False) -> str | None:
        value = query.get(name, [""])[0].strip()
        if required and not value:
            raise ValueError(f"missing required parameter: {name}")
        if len(value) > maximum:
            raise ValueError(f"parameter {name} exceeds {maximum} characters")
        return value or None

    def _read_json_body(self, max_bytes: int = 5_000_000) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError:
            raise ValueError("Content-Length must be an integer")
        if length < 0 or length > max_bytes:
            raise ValueError(f"request body exceeds {max_bytes} bytes")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON body: {exc}")
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_POST(self) -> None:
        if not self._is_localhost():
            self._send_error_json(403, "forbidden", "Access restricted to localhost.")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        try:
            body = self._read_json_body()
            if path == "/context":
                request = ContextRequest.from_dict(body)
                adapter = None
                if request.freshness.allow_live_acquisition and (request.target or request.current_session):
                    adapter = acquire_current_conversation_via_camofox
                self._send_json(200, run_context_request(self.db, request, adapter=adapter, max_attempts=1))
                return

            if path == "/handoff/redeem":
                handoff_id = str(body.get("handoff_id") or "").strip()
                if not handoff_id:
                    raise ValueError("handoff_id is required")
                row = self.db.redeem_context_handoff(
                    handoff_id,
                    consumer_session_id=(
                        str(body.get("consumer_session_id")).strip()
                        if body.get("consumer_session_id") else None
                    ),
                )
                request = ContextRequest.from_dict(
                    {
                        "consumer": "hermes-context-engine",
                        "session_id": row["consumer_session_id"],
                        "query": "",
                        "intent": "retrieve",
                        "target": {
                            "type": "conversation",
                            "conversation_uid": row["conversation_uid"],
                            "snapshot": "explicit",
                            "snapshot_id": row["snapshot_id"],
                            "transcript_mode": "active_chain",
                        },
                        "freshness": {
                            "mode": "accept_stale",
                            "allow_live_acquisition": False,
                        },
                        "budget": {
                            "max_messages": int(body.get("max_messages") or 30),
                            "max_bytes": int(body.get("max_bytes") or 120000),
                        },
                        "trust": "historical_evidence",
                    }
                )
                bundle = resolve_context_request(self.db, request)
                bundle["handoff"] = {
                    "status": "redeemed",
                    "handoff_id": handoff_id,
                    "consumer_session_id": row["consumer_session_id"],
                    "conversation_uid": row["conversation_uid"],
                    "snapshot_id": row["snapshot_id"],
                    "created_at": row["created_at"],
                    "expires_at": row["expires_at"],
                    "raw_host_identity_returned": False,
                }
                self._send_json(200, bundle)
                return

            if path == "/acquisition/ingest":
                payload = body.get("payload")
                if not isinstance(payload, dict):
                    raise ValueError("payload must be an object")
                result = ingest_conversation_payload(
                    payload,
                    project_id=str(body.get("project_id") or ""),
                    project_name=str(body.get("project_name") or ""),
                    provider=str(body.get("provider") or "chatgpt"),
                    account_id=str(body.get("account_id") or "default"),
                    acquisition_method=str(body.get("acquisition_method") or "manual"),
                    db=self.db,
                    raw_dir=self.raw_dir,
                )
                self._send_json(200, result)
                return

            self._send_error_json(404, "not_found", f"Endpoint '{path}' not found.")
        except ValueError as exc:
            self._send_error_json(400, "bad_request", str(exc))
        except Exception as exc:
            self._send_error_json(500, "internal_error", str(exc))

    def do_GET(self) -> None:
        if not self._is_localhost():
            self._send_error_json(403, "forbidden", "Access restricted to localhost.")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/health":
                self._send_json(200, {"status": "ok", "version": "0.3.0"})
                return
            if path == "/projects":
                self._send_json(200, self.db.projects())
                return
            if path.startswith("/projects/") and path.endswith("/conversations"):
                parts = path.split("/")
                if len(parts) == 4:
                    self._send_json(200, self.db.conversations(project_id=parts[2]))
                    return
            if path.startswith("/projects/") and path.endswith("/context"):
                parts = path.split("/")
                if len(parts) == 4:
                    topic = self._param(query, "topic", 300)
                    provider = self._param(query, "provider", 100)
                    account_id = self._param(query, "account", 200)
                    limit = self._limit(query)
                    self._send_json(
                        200,
                        project_context(
                            self.db,
                            parts[2],
                            topic=topic,
                            limit=limit,
                            provider=provider,
                            account_id=account_id,
                        ),
                    )
                    return
            if path.startswith("/projects/") and path.endswith("/timeline"):
                parts = path.split("/")
                if len(parts) == 4:
                    provider = self._param(query, "provider", 100)
                    account_id = self._param(query, "account", 200)
                    limit = self._limit(query, default=10)
                    self._send_json(
                        200,
                        timeline(
                            self.db,
                            parts[2],
                            limit=limit,
                            provider=provider,
                            account_id=account_id,
                        ),
                    )
                    return
            if path.startswith("/conversations/"):
                parts = path.split("/")
                if len(parts) == 3:
                    item = self.db.get(parts[2])
                    if not item:
                        self._send_error_json(404, "not_found", f"Conversation '{parts[2]}' not found.")
                        return
                    self._send_json(200, item)
                    return
            if path.startswith("/snapshots/"):
                parts = path.split("/")
                if len(parts) == 3:
                    item = self.db.get_snapshot(parts[2])
                    if not item:
                        self._send_error_json(404, "not_found", f"Snapshot '{parts[2]}' not found.")
                        return
                    self._send_json(200, item)
                    return
            if path.startswith("/conversations/") and path.endswith("/snapshots"):
                parts = path.split("/")
                if len(parts) == 4:
                    self._send_json(200, self.db.snapshots(parts[2]))
                    return
            if path == "/search":
                q = self._param(query, "q", 500, required=True)
                limit = self._limit(query, default=20)
                project = self._param(query, "project", 200)
                provider = self._param(query, "provider", 100)
                account_id = self._param(query, "account", 200)
                resolved_project = None
                if project:
                    for p in self.db.projects():
                        if p["project_uid"] == project or p["id"] == project or p["name"].strip().lower() == project.lower():
                            resolved_project = p["project_uid"]
                            break
                self._send_json(
                    200,
                    self.db.search_detailed(
                        q,
                        limit=limit,
                        project_id=resolved_project,
                        provider=provider,
                        account_id=account_id,
                    ),
                )
                return
            if path == "/continuity":
                q = self._param(query, "q", 500, required=True)
                project = self._param(query, "project", 200)
                provider = self._param(query, "provider", 100)
                account_id = self._param(query, "account", 200)
                limit = self._limit(query)
                self._send_json(
                    200,
                    continuity(
                        self.db,
                        q,
                        project=project,
                        limit=limit,
                        provider=provider,
                        account_id=account_id,
                    ),
                )
                return
            if path == "/compare":
                raw_ids = self._param(query, "ids", 1000, required=True)
                ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
                self._send_json(200, compare(self.db, ids))
                return
            self._send_error_json(404, "not_found", f"Endpoint '{path}' not found.")
        except ValueError as exc:
            code = 409 if "ambiguous" in str(exc).lower() else 400
            self._send_error_json(code, "ambiguous" if code == 409 else "bad_request", str(exc))
        except KeyError as exc:
            self._send_error_json(404, "not_found", str(exc))
        except Exception as exc:
            self._send_error_json(500, "internal_error", str(exc))


def create_server(
    host="127.0.0.1",
    port=8765,
    db: ArchiveDB | None = None,
    db_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
) -> HTTPServer:
    if db is None:
        db = ArchiveDB(get_db_path(db_path), check_same_thread=False)
    resolved_raw_dir = Path(raw_dir) if raw_dir is not None else get_raw_dir()

    class CustomHandler(GatewayRequestHandler):
        pass

    CustomHandler.db = db
    CustomHandler.raw_dir = resolved_raw_dir
    return HTTPServer((host, port), CustomHandler)


def run_server(
    host="127.0.0.1",
    port=8765,
    db: ArchiveDB | None = None,
    db_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        db=db,
        db_path=db_path,
        raw_dir=raw_dir,
    )
    print(f"Context Gateway retrieval server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()
