"""CSV read/write helpers, all paths resolved against config.DATA_DIR."""
from pathlib import Path

import pandas as pd

from . import config


def _path(filename: str) -> Path:
    return Path(config.DATA_DIR) / filename


def load_tracker_list() -> pd.DataFrame:
    return pd.read_csv(_path("tracker_list.csv"))


def load_zone_list() -> pd.DataFrame:
    return pd.read_csv(_path("zone_list.csv"))


def load_zone_detail() -> pd.DataFrame:
    return pd.read_csv(_path("zone_detail_all_df.csv"))


def load_gps_data(filename: str = "gps_data.csv") -> pd.DataFrame:
    return pd.read_csv(_path(filename))


def save_csv(df: pd.DataFrame, filename: str, index: bool = False) -> Path:
    out = _path(filename)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=index)
    return out
