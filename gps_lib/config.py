"""Environment configuration, loaded once from .env at project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

NAVIXY_BASE_URL = os.environ.get("NAVIXY_BASE_URL", "https://api.gaikham.com")
NAVIXY_LOGIN = os.environ.get("NAVIXY_LOGIN")
NAVIXY_PASSWORD = os.environ.get("NAVIXY_PASSWORD")

# Defaults to the repo-local data/ dir; override via GPS_DATA_DIR in .env to
# point at an external copy (e.g. OneDrive) instead of duplicating large CSVs.
DATA_DIR = Path(os.environ.get("GPS_DATA_DIR", PROJECT_ROOT / "data"))


def require_credentials() -> None:
    if not NAVIXY_LOGIN or not NAVIXY_PASSWORD:
        raise RuntimeError(
            "NAVIXY_LOGIN / NAVIXY_PASSWORD are not set. Copy .env.example to "
            ".env and fill in real credentials."
        )
