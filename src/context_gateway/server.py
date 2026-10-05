import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .config import get_db_path
from .continuity import compare, continuity, project_context, timeline
from .db import ArchiveDB

class GatewayRequestHandler(BaseHTTPRequestHandler):
    db: ArchiveDB

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

    def do_GET(self) -> None:
        if not self._is_localhost():
            self._send_error_json(403, "forbidden", "Access restricted to localhost.")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/health":
                self._send_json(200, {"status": "ok", "version": "0.2.1"})
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
                    limit = self._limit(query)
                    self._send_json(200, project_context(self.db, parts[2], topic=topic, limit=limit))
                    return

            if path.startswith("/projects/") and path.endswith("/timeline"):
                parts = path.split("/")
                if len(parts) == 4:
                    limit = self._limit(query, default=10)
                    self._send_json(200, timeline(self.db, parts[2], limit=limit))
                    return

            if path.startswith("/conversations/"):
                parts = path.split("/")
                if len(parts) == 3:
                    item = self.db.get(parts[2])
                    if not item:
                        self._send_error_json(404, "not_found", f"Conversation '{parts[2]}' not found.")
                        return
                    if isinstance(item.get("raw_json"), str):
                        try:
                            item["raw_json"] = json.loads(item["raw_json"])
                        except Exception:
                            pass
                    self._send_json(200, item)
                    return

            if path == "/search":
                q = self._param(query, "q", 500, required=True)
                limit = self._limit(query, default=20)
                project = self._param(query, "project", 200)
                project_id = None
                if project:
                    for p in self.db.projects():
                        if p["id"] == project or p["name"].strip().lower() == project.lower():
                            project_id = p["id"]
                            break
                self._send_json(200, self.db.search_detailed(q, limit=limit, project_id=project_id))
                return

            if path == "/continuity":
                q = self._param(query, "q", 500, required=True)
                project = self._param(query, "project", 200)
                limit = self._limit(query)
                self._send_json(200, continuity(self.db, q, project=project, limit=limit))
                return

            if path == "/compare":
                raw_ids = self._param(query, "ids", 1000, required=True)
                ids = [x.strip() for x in raw_ids.split(",") if x.strip()]
                self._send_json(200, compare(self.db, ids))
                return

            self._send_error_json(404, "not_found", f"Endpoint '{path}' not found.")
        except KeyError as exc:
            self._send_error_json(404, "not_found", str(exc))
        except ValueError as exc:
            self._send_error_json(400, "bad_request", str(exc))
        except Exception as exc:
            self._send_error_json(500, "internal_error", str(exc))

def create_server(host="127.0.0.1", port=8765, db: ArchiveDB | None = None, db_path: str | Path | None = None) -> HTTPServer:
    if db is None:
        db = ArchiveDB(get_db_path(db_path), check_same_thread=False)

    class CustomHandler(GatewayRequestHandler):
        pass

    CustomHandler.db = db
    return HTTPServer((host, port), CustomHandler)

def run_server(host="127.0.0.1", port=8765, db: ArchiveDB | None = None, db_path: str | Path | None = None) -> None:
    server = create_server(host=host, port=port, db=db, db_path=db_path)
    print(f"Context Gateway retrieval server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()
