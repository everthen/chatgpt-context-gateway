__version__ = "0.2.1"

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
from .db import ArchiveDB
from .normalize import extract_text, make_record, stable_hash
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
    "extract_text",
    "make_record",
    "stable_hash",
    "create_server",
    "run_server",
    "sync_project",
    "sync_projects",
]
