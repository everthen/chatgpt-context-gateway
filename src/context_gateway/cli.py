from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .client import AuthenticationError, ChatGPTClient, ChatGPTClientError
from .config import get_db_path, get_raw_dir
from .connect import DEFAULT_ENV_PATH, run_connect
from .continuity import continuity
from .db import ArchiveDB
from .mcp_server import run_mcp
from .openai_export import OpenAIExportError, import_openai_export
from .server import run_server
from .sync import sync_project, sync_projects


def format_timestamp(ts: float | int | str | None) -> str:
    if ts is None:
        return "-"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


def cmd_projects(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    try:
        projects = ChatGPTClient(env_file=args.env_file).list_projects() if args.remote else db.projects()
    except AuthenticationError as e:
        print(f"Authentication error: {e}", file=sys.stderr)
        return 1
    except ChatGPTClientError as e:
        print(f"ChatGPT API error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()

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
    try:
        if args.project:
            print(f"Syncing project '{args.project}'...")
            records = sync_project(
                project_name=args.project,
                client=client,
                db=db,
                raw_dir=get_raw_dir(args.raw_dir),
                env_file=args.env_file,
            )
            print(f"Successfully synced {len(records)} conversation(s) for project '{args.project}'.")
        else:
            print("Syncing all projects...")
            summary = sync_projects(
                client=client,
                db=db,
                raw_dir=get_raw_dir(args.raw_dir),
                env_file=args.env_file,
            )
            total = sum(summary.values())
            print(f"Sync complete. Synced {len(summary)} project(s), {total} total conversation(s).")
        return 0
    except Exception as e:
        print(f"Sync failed: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_chats(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    try:
        target_project_id: str | None = None
        if args.project:
            projs = db.projects()
            matched = next(
                (
                    p for p in projs
                    if p["project_uid"] == args.project
                    or p["id"] == args.project
                    or p["name"].strip().lower() == args.project.strip().lower()
                ),
                None,
            )
            if not matched:
                print(f"Project '{args.project}' not found in database.", file=sys.stderr)
                return 1
            target_project_id = matched["project_uid"]

        convs = db.conversations(project_id=target_project_id)
        if not convs:
            print("No conversations found.")
            return 0

        print(f"{'CONVERSATION ID':<38} {'PROJECT':<20} {'TITLE':<30} {'UPDATED AT'}")
        print("-" * 108)
        for c in convs:
            print(
                f"{(c.get('id') or '-'):<38} "
                f"{(c.get('project_name') or '-'):<20} "
                f"{(c.get('title') or 'Untitled')[:28]:<30} "
                f"{format_timestamp(c.get('update_time') or c.get('create_time'))}"
            )
        return 0
    finally:
        db.close()


def cmd_get(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    try:
        conv = db.get(args.conversation_id)
        if not conv:
            print(f"Conversation '{args.conversation_id}' not found.", file=sys.stderr)
            return 1
        if args.full:
            print(json.dumps(conv, ensure_ascii=False, indent=2))
            return 0
        print(f"ID:             {conv.get('id')}")
        print(f"Conversation UID:{conv.get('conversation_uid')}")
        print(f"Title:          {conv.get('title')}")
        print(f"Provider/Acct:  {conv.get('provider')}/{conv.get('account_id')}")
        print(f"Snapshot:       {conv.get('current_snapshot', {}).get('snapshot_id')}")
        print(f"Raw Path:       {conv.get('raw_path')}")
        print("-" * 60)
        for msg in conv.get("messages", []):
            print(f"[{msg.get('role')}] {msg.get('message_id')}:")
            print(msg.get("text", ""))
            print()
        return 0
    finally:
        db.close()


def cmd_search(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    try:
        results = db.search_messages(args.query, limit=args.limit)
    finally:
        db.close()
    if not results:
        print(f"No results found for query: {args.query!r}")
        return 0

    print(f"Found {len(results)} matching message(s):")
    print(f"{'CONVERSATION ID':<38} {'MESSAGE':<24} {'PROVIDER/ACCOUNT':<24} {'TITLE'}")
    print("-" * 120)
    for r in results:
        print(
            f"{r.get('id'):<38} "
            f"{r.get('message_id'):<24} "
            f"{r.get('provider')}/{r.get('account_id'):<24} "
            f"{r.get('title') or 'Untitled'}"
        )
    return 0


def cmd_continuity(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    try:
        result = continuity(db, args.query, project=args.project, limit=args.limit)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    run_server(
        host=args.host,
        port=args.port,
        db_path=get_db_path(args.db),
        raw_dir=get_raw_dir(args.raw_dir),
    )
    return 0


def cmd_mcp_serve(args: argparse.Namespace) -> int:
    run_mcp(db_path=get_db_path(args.db), host=args.host, port=args.port)
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    try:
        return run_connect(
            env_path=args.env_file or DEFAULT_ENV_PATH,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )
    except (OSError, ValueError) as exc:
        print(f"Connect flow failed: {exc}", file=sys.stderr)
        return 1


def cmd_import_openai(args: argparse.Namespace) -> int:
    db = ArchiveDB(get_db_path(args.db))
    try:
        summary = import_openai_export(
            source=args.source,
            account_id=args.account_id,
            db=db,
            raw_dir=get_raw_dir(args.raw_dir),
        )
    except OpenAIExportError as exc:
        print(f"OpenAI export import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    total = sum(summary.values())
    print(f"Imported {total} conversation(s) into account '{args.account_id}'.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatgpt-context",
        description="Local-first universal AI context archive and retrieval gateway",
    )
    parser.add_argument("--db", default=None)
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--env-file", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("projects")
    p.add_argument("--remote", action="store_true")
    p.set_defaults(func=cmd_projects)

    p = subparsers.add_parser("sync")
    p.add_argument("--project", "-p", default=None)
    p.set_defaults(func=cmd_sync)

    p = subparsers.add_parser("chats")
    p.add_argument("--project", "-p", default=None)
    p.set_defaults(func=cmd_chats)

    p = subparsers.add_parser("get")
    p.add_argument("--conversation-id", "-c", required=True)
    p.add_argument("--full", action="store_true")
    p.set_defaults(func=cmd_get)

    p = subparsers.add_parser("search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = subparsers.add_parser("continuity")
    p.add_argument("query")
    p.add_argument("--project", "-p", default=None)
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(func=cmd_continuity)

    p = subparsers.add_parser("serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_serve)

    p = subparsers.add_parser("mcp-serve")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p.set_defaults(func=cmd_mcp_serve)

    p = subparsers.add_parser("connect")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8780)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_connect)

    p = subparsers.add_parser("import-openai")
    p.add_argument("source")
    p.add_argument("--account-id", required=True)
    p.set_defaults(func=cmd_import_openai)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
