"""Client for the Navixy-style GPS tracking API (gaikham.com).

Consolidates logic that was previously copy-pasted across get_GPS_trackpoint.ipynb
and get_gps_zone.ipynb (which also had a domain typo, api.gaikhams.com vs
api.gaikham.com, in one of its two navixy_auth() copies).
"""
import time
from typing import Optional

import pandas as pd
import requests

from . import config


def authenticate() -> str:
    """Log in and return a session hash token."""
    config.require_credentials()
    url = f"{config.NAVIXY_BASE_URL}/user/auth"
    response = requests.post(
        url,
        json={"login": config.NAVIXY_LOGIN, "password": config.NAVIXY_PASSWORD},
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Navixy auth failed ({response.status_code}): {response.text}")
    hash_token = response.json().get("hash")
    if not hash_token:
        raise RuntimeError("Navixy auth succeeded but no hash token was returned.")
    return hash_token


def _post(endpoint: str, hash_token: str, payload: Optional[dict] = None,
          timeout: int = 10, _retried: bool = False) -> dict:
    url = f"{config.NAVIXY_BASE_URL}{endpoint}"
    body = {"hash": hash_token, **(payload or {})}
    response = requests.post(url, json=body, timeout=timeout)
    if response.status_code != 200:
        # A stale/expired hash token is the common cause of 401/403 here;
        # re-authenticate once and retry before giving up.
        if not _retried and response.status_code in (401, 403):
            fresh_token = authenticate()
            return _post(endpoint, fresh_token, payload, timeout, _retried=True)
        raise RuntimeError(f"{endpoint} failed ({response.status_code}): {response.text}")
    return response.json()


def get_tracker_list(hash_token: str) -> pd.DataFrame:
    """Fetch the full tracker/vehicle list."""
    data = _post("/tracker/list", hash_token)
    return pd.json_normalize(data.get("list", []), sep="_")


def get_track_read(hash_token: str, tracker_id: int, from_time: str, to_time: str,
                    max_retries: int = 3) -> Optional[pd.DataFrame]:
    """Fetch GPS pings for one tracker over a time range, retrying on transient errors."""
    payload = {
        "tracker_id": tracker_id,
        "from": from_time,
        "to": to_time,
        "filter": False,
        "simplify": False,
        "include_gsm_lbs": True,
    }
    for attempt in range(1, max_retries + 1):
        try:
            data = _post("/track/read", hash_token, payload, timeout=60)
            items = data.get("list", [])
            return pd.json_normalize(items, sep="_") if items else None
        except (requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            print(f"  tracker {tracker_id}: connection error on attempt {attempt}/{max_retries}: {exc}")
            if attempt < max_retries:
                time.sleep(2)
            else:
                print(f"  tracker {tracker_id}: failed after {max_retries} attempts")
                return None
        except RuntimeError as exc:
            print(f"  tracker {tracker_id}: {exc}")
            return None
    return None


def get_zone_list(hash_token: str) -> pd.DataFrame:
    """Fetch all defined mine zones (load/dump/fuel/repair/etc.)."""
    data = _post("/zone/list", hash_token)
    return pd.json_normalize(data.get("list", []), sep="_")


def get_zone_detail_list(hash_token: str, zone_id: int) -> Optional[pd.DataFrame]:
    """Fetch polygon vertices for a single zone."""
    data = _post("/zone/point/list", hash_token, {"zone_id": zone_id})
    items = data.get("list", [])
    return pd.json_normalize(items, sep="_") if items else None
