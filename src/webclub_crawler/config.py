import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

DEFAULT_CLUB_ID = "1"
DEFAULT_BASE_URL = os.getenv("WEBCLUB_BASE_URL")
DEFAULT_OUTPUT_DIR = Path.cwd()


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def resolve_base_url(base_url: str | None = None) -> str:
    resolved_base_url = (base_url or DEFAULT_BASE_URL or "").strip()
    if not resolved_base_url:
        raise ValueError("WEBCLUB_BASE_URL must be set in .env or passed as base_url.")
    return normalize_base_url(resolved_base_url)


def get_credentials(username: str | None = None, password: str | None = None) -> tuple[str | None, str | None]:
    return username or os.getenv("WEBCLUB_USER"), password or os.getenv("WEBCLUB_PASSWORD")
