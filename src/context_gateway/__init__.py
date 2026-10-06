__version__ = "0.3.0"

from .client import (
    ChatGPTClient,
    ChatGPTClientError,
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    load_env_file,
)
from .config import (
    get_db_path,
    get_raw_dir,
    safe_project_name,
)
from .account import account_status, begin_chatgpt_login, wait_for_chatgpt_login
from .acquisition import (
    acquire_hot_tail_via_camofox,
    ingest_camofox_observation,
    ingest_conversation_payload,
    run_hot_context_request,
)
from .camofox import CamofoxClient, CamofoxObservation, BrowserTurn, capture_latest_view, collect_conversation, parse_visible_turns
from .contracts import AcquisitionCheckpoint, AcquisitionPolicy, ContextBudget, ContextRequest, ContextScope, FreshnessPolicy
from .db import ArchiveDB
from .normalize import extract_messages, extract_text, make_record, messages_from_indexed_text, stable_hash
from .server import create_server, run_server
from .sync import sync_project, sync_projects

__all__ = [
    "__version__",
    "ChatGPTClient",
    "ChatGPTClientError",
    "AuthenticationError",
    "NotFoundError",
    "RateLimitError",
    "load_env_file",
    "get_db_path",
    "get_raw_dir",
    "safe_project_name",
    "ArchiveDB",
    "ContextRequest",
    "ContextScope",
    "AcquisitionPolicy",
    "ContextBudget",
    "FreshnessPolicy",
    "AcquisitionCheckpoint",
    "BrowserTurn",
    "CamofoxClient",
    "CamofoxObservation",
    "collect_conversation",
    "capture_latest_view",
    "parse_visible_turns",
    "ingest_conversation_payload",
    "ingest_camofox_observation",
    "acquire_hot_tail_via_camofox",
    "run_hot_context_request",
    "account_status",
    "begin_chatgpt_login",
    "wait_for_chatgpt_login",
    "extract_messages",
    "extract_text",
    "messages_from_indexed_text",
    "make_record",
    "stable_hash",
    "create_server",
    "run_server",
    "sync_project",
    "sync_projects",
]
