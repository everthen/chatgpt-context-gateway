import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .client import AuthenticationError, ChatGPTClient, ChatGPTClientError
from .config import get_db_path, get_raw_dir
from .db import ArchiveDB
from .server import run_server
from .mcp_server import run_mcp
from .openai_export import OpenAIExportError, import_openai_export
from .sync import sync_project, sync_projects

def format_timestamp(ts: float | int | str | None) -> str:
    if ts is None:
        return "-"
    try:
        val = float(ts)
        return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)

def cmd_projects(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    if getattr(args, "remote", False):
        try:
            client = ChatGPTClient(env_file=args.env_file)
            projects = client.list_projects()
        except AuthenticationError as e:
            print(f"Authentication error: {e}", file=sys.stderr)
            return 1
        except ChatGPTClientError as e:
            print(f"ChatGPT API error: {e}", file=sys.stderr)
            return 1
    else:
        projects = db.projects()

    if not projects:
        print("No projects found.")
        return 0

    print(f"{'PROJECT ID':<38} {'NAME':<30} {'UPDATED AT'}")
    print("-" * 88)
    for p in projects:
        pid = p.get("id") or "-"
        name = p.get("name") or "-"
        updated = format_timestamp(p.get("updated_at") or p.get("created_at"))
        print(f"{pid:<38} {name:<30} {updated}")
    return 0

def cmd_sync(args: argparse.Namespace) -> int:
    try:
        client = ChatGPTClient(env_file=args.env_file)
    except AuthenticationError as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        return 1

    db = ArchiveDB(get_db_path(args.db))
    raw_dir = get_raw_dir(args.raw_dir)

    try:
        if args.project:
            print(f"Syncing project '{args.project}'...")
            records = sync_project(
                project_name=args.project,
                client=client,
                db=db,
                raw_dir=raw_dir,
                env_file=args.env_file,
            )
            print(f"Successfully synced {len(records)} conversation(s) for project '{args.project}'.")
        else:
            print("Syncing all projects...")
            summary = sync_projects(
                client=client,
                db=db,
                raw_dir=raw_dir,
                env_file=args.env_file,
            )
            total = sum(summary.values())
            print(f"Sync complete. Synced {len(summary)} project(s), {total} total conversation(s).")
            for proj_name, count in summary.items():
                print(f"  - {proj_name}: {count} conversation(s)")
        return 0
    except Exception as e:
        print(f"Sync failed: {e}", file=sys.stderr)
        return 1

def cmd_chats(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    target_project_id: str | None = None

    if args.project:
        projs = db.projects()
        matched = None
        for p in projs:
            if p["id"] == args.project or p["name"].strip().lower() == args.project.strip().lower():
                matched = p
                break
        if not matched:
            print(f"Project '{args.project}' not found in database.", file=sys.stderr)
            return 1
        target_project_id = matched["id"]

    convs = db.conversations(project_id=target_project_id)
    if not convs:
        print("No conversations found.")
        return 0

    print(f"{'CONVERSATION ID':<38} {'PROJECT':<20} {'TITLE':<30} {'UPDATED AT'}")
    print("-" * 108)
    for c in convs:
        cid = c.get("id") or "-"
        proj = c.get("project_name") or "-"
        title = (c.get("title") or "Untitled")[:28]
        updated = format_timestamp(c.get("update_time") or c.get("create_time"))
        print(f"{cid:<38} {proj:<20} {title:<30} {updated}")
    return 0

def cmd_get(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    conv = db.get(args.conversation_id)
    if not conv:
        print(f"Conversation '{args.conversation_id}' not found.", file=sys.stderr)
        return 1

    if getattr(args, "full", False):
        raw = conv.get("raw_json")
        if raw:
            try:
                parsed = json.loads(raw)
                print(json.dumps(parsed, ensure_ascii=False, indent=2))
            except Exception:
                print(raw)
        else:
            print("{}")
        return 0

    print(f"ID:           {conv.get('id')}")
    print(f"Title:        {conv.get('title')}")
    print(f"Project:      {conv.get('project_name')} ({conv.get('project_id')})")
    print(f"Updated At:   {format_timestamp(conv.get('update_time'))}")
    print(f"Raw Path:     {conv.get('raw_path')}")
    print("-" * 60)
    print("INDEXED TEXT:")
    print("-" * 60)
    print(conv.get("indexed_text", ""))
    return 0

def cmd_search(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    results = db.search(args.query, limit=args.limit)
    if not results:
        print(f"No results found for query: {args.query!r}")
        return 0

    print(f"Found {len(results)} matching conversation(s):")
    print(f"{'CONVERSATION ID':<38} {'PROJECT':<20} {'TITLE':<30} {'UPDATED AT'}")
    print("-" * 108)
    for r in results:
        cid = r.get("id") or "-"
        proj = r.get("project_name") or "-"
        title = (r.get("title") or "Untitled")[:28]
        updated = format_timestamp(r.get("update_time"))
        print(f"{cid:<38} {proj:<20} {title:<30} {updated}")
    return 0

def cmd_serve(args: argparse.Namespace) -> int:
    run_server(host=args.host, port=args.port, db_path=get_db_path(args.db))
    return 0

def cmd_mcp_serve(args: argparse.Namespace) -> int:
    run_mcp(db_path=get_db_path(args.db), host=args.host, port=args.port)
    return 0

def cmd_import_openai(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    raw_dir = get_raw_dir(args.raw_dir)
    try:
        summary = import_openai_export(
            source=args.source,
            account_id=args.account_id,
            db=db,
            raw_dir=raw_dir,
        )
    except OpenAIExportError as exc:
        print(f"OpenAI export import failed: {exc}", file=sys.stderr)
        return 1
    total = sum(summary.values())
    print(f"Imported {total} conversation(s) into account '{args.account_id}'.")
    for project, count in summary.items():
        print(f"  - {project}: {count}")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt-context",
        description="Local-first archive and retrieval gateway for ChatGPT conversations",
    )
    parser.add_argument("--db", default=None, help="Path to SQLite archive database")
    parser.add_argument("--raw-dir", default=None, help="Directory for raw conversation JSON payloads")
    parser.add_argument("--env-file", default=None, help="Path to external environment file with ChatGPT credentials")

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_proj = subparsers.add_parser("projects", help="List projects")
    p_proj.add_argument("--remote", action="store_true", help="Fetch projects live from ChatGPT instead of local DB")
    p_proj.set_defaults(func=cmd_projects)

    p_sync = subparsers.add_parser("sync", help="Sync projects and conversations from ChatGPT")
    p_sync.add_argument("--project", "-p", default=None, help="Specific project name or ID to sync")
    p_sync.set_defaults(func=cmd_sync)

    p_chats = subparsers.add_parser("chats", help="List conversations in a project or all projects")
    p_chats.add_argument("--project", "-p", default=None, help="Filter conversations by project name or ID")
    p_chats.set_defaults(func=cmd_chats)

    p_get = subparsers.add_parser("get", help="Get a conversation by ID")
    p_get.add_argument("--conversation-id", "-c", required=True, help="Conversation ID to retrieve")
    p_get.add_argument("--full", action="store_true", help="Output full raw JSON payload")
    p_get.set_defaults(func=cmd_get)

    p_search = subparsers.add_parser("search", help="Search conversations using full-text index")
    p_search.add_argument("query", help="Full-text search query")
    p_search.add_argument("--limit", type=int, default=20, help="Maximum number of results (default: 20)")
    p_search.set_defaults(func=cmd_search)

    p_serve = subparsers.add_parser("serve", help="Run localhost retrieval HTTP API server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host address to bind (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=8765, help="Port to bind (default: 8765)")
    p_serve.set_defaults(func=cmd_serve)

    p_mcp = subparsers.add_parser("mcp-serve", help="Run read-only MCP Streamable HTTP server")
    p_mcp.add_argument("--host", default="127.0.0.1", help="Host address to bind")
    p_mcp.add_argument("--port", type=int, default=8766, help="Port to bind")
    p_mcp.set_defaults(func=cmd_mcp_serve)

    p_import = subparsers.add_parser("import-openai", help="Import a ChatGPT/OpenAI data export")
    p_import.add_argument("source", help="Path to conversations.json, JSON export directory, or ZIP export")
    p_import.add_argument("--account-id", required=True, help="Stable local account identifier")
    p_import.set_defaults(func=cmd_import_openai)

    return parser

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
