import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .config import get_db_path
from .db import ArchiveDB

class GatewayRequestHandler(BaseHTTPRequestHandler):
    db: ArchiveDB

    def log_message(self, format: str, *args: Any) -> None:
        # Keep server quiet during tests or normal operation
        pass

    def _is_localhost(self) -> bool:
        client_ip = self.client_address[0]
        return client_ip in ("127.0.0.1", "::1", "localhost", "testclient")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, error_code: str, message: str) -> None:
        self._send_json(status, {"error": error_code, "message": message})

    def do_GET(self) -> None:
        if not self._is_localhost():
            self._send_error_json(403, "forbidden", "Access restricted to localhost.")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        # GET /health
        if path == "/health":
            self._send_json(200, {"status": "ok", "version": "0.1.0"})
            return

        # GET /projects
        if path == "/projects":
            projects = self.db.projects()
            self._send_json(200, projects)
            return

        # GET /projects/{project_id}/conversations
        if path.startswith("/projects/") and path.endswith("/conversations"):
            parts = path.split("/")
            # path is "/projects/<project_id>/conversations"
            if len(parts) == 4 and parts[1] == "projects" and parts[3] == "conversations":
                project_id = parts[2]
                convs = self.db.conversations(project_id=project_id)
                self._send_json(200, convs)
                return

        # GET /conversations/{conversation_id}
        if path.startswith("/conversations/"):
            parts = path.split("/")
            if len(parts) == 3 and parts[1] == "conversations":
                conversation_id = parts[2]
                conv = self.db.get(conversation_id)
                if not conv:
                    self._send_error_json(404, "not_found", f"Conversation '{conversation_id}' not found.")
                    return
                # Optionally parse raw_json string to avoid double-encoding
                if "raw_json" in conv and isinstance(conv["raw_json"], str):
                    try:
                        conv["raw_json"] = json.loads(conv["raw_json"])
                    except Exception:
                        pass
                self._send_json(200, conv)
                return

        # GET /search?q=
        if path == "/search":
            q_list = query.get("q")
            if not q_list or not q_list[0].strip():
                self._send_error_json(400, "bad_request", "Missing required query parameter: q")
                return

            q = q_list[0].strip()
            limit = 20
            if "limit" in query:
                try:
                    limit = int(query["limit"][0])
                except ValueError:
                    pass

            results = self.db.search(q, limit=limit)
            self._send_json(200, results)
            return

        self._send_error_json(404, "not_found", f"Endpoint '{path}' not found.")

def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db: ArchiveDB | None = None,
    db_path: str | Path | None = None,
) -> HTTPServer:
    if db is None:
        db = ArchiveDB(get_db_path(db_path), check_same_thread=False)

    class CustomHandler(GatewayRequestHandler):
        pass

    CustomHandler.db = db

    server = HTTPServer((host, port), CustomHandler)
    return server

def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db: ArchiveDB | None = None,
    db_path: str | Path | None = None,
) -> None:
    server = create_server(host=host, port=port, db=db, db_path=db_path)
    print(f"ChatGPT Context Gateway retrieval server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()
