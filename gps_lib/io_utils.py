"""CSV read/write helpers, all paths resolved against config.DATA_DIR."""
import re
from pathlib import Path

import pandas as pd

from . import config

_MONTHLY_GPS_DATA_RE = re.compile(r"^gps_data_\d{4}-\d{1,2}\.csv$")


def _path(filename: str) -> Path:
    return Path(config.DATA_DIR) / filename


def load_tracker_list() -> pd.DataFrame:
    return pd.read_csv(_path("tracker_list.csv"))


def load_zone_list() -> pd.DataFrame:
    return pd.read_csv(_path("zone_list.csv"))


def load_zone_detail() -> pd.DataFrame:
    return pd.read_csv(_path("zone_detail_all_df.csv"))


# def load_gps_data(filename: str = "gps_data.csv") -> pd.DataFrame:
#     return pd.read_csv(_path(filename))


def load_gps_data_sample(filename: str = "gps_data_sample.csv") -> pd.DataFrame:
    return pd.read_csv(_path(filename))


def load_gps_data() -> pd.DataFrame:
    """Concatenate every per-month gps_data_<year>-<month>.csv file in DATA_DIR."""
    files = sorted(
        p for p in Path(config.DATA_DIR).glob("gps_data_*.csv")
        if _MONTHLY_GPS_DATA_RE.match(p.name)
    )
    if not files:
        raise FileNotFoundError(
            f"No gps_data_<year>-<month>.csv files found in {config.DATA_DIR}"
        )
    return pd.concat((pd.read_csv(f) for f in files), ignore_index=True)


def save_csv(df: pd.DataFrame, filename: str, index: bool = False) -> Path:
    out = _path(filename)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=index)
    return out
