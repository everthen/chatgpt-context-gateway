import os
import re
from pathlib import Path

DEFAULT_DATA_DIR = Path("data")
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "archive.sqlite3"
DEFAULT_RAW_DIR = DEFAULT_DATA_DIR / "raw"
DEFAULT_CAMOFOX_PROFILE_ID = "camofox-human-login"

def get_camofox_profile_id(override: str | None = None) -> str:
    if override:
        return override
    return os.environ.get("CAMOFOX_PROFILE_ID", DEFAULT_CAMOFOX_PROFILE_ID)

def get_db_path(override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    env_path = os.environ.get("CHATGPT_GATEWAY_DB")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH

def get_raw_dir(override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    env_dir = os.environ.get("CHATGPT_GATEWAY_RAW_DIR")
    if env_dir:
        return Path(env_dir)
    return DEFAULT_RAW_DIR

def safe_project_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", name.strip())
    cleaned = cleaned.strip("_")
    return cleaned if cleaned else "default"
