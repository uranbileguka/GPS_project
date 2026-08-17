"""CSV read/write helpers, all paths resolved against config.DATA_DIR."""
import re
from pathlib import Path
from typing import List, Optional, Union

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


def load_gps_data(months: Optional[Union[str, List[str]]] = None) -> pd.DataFrame:
    """Concatenate per-month gps_data_<year>-<month>.csv file(s) in DATA_DIR.

    months: one "<year>-<month>" string (e.g. "2025-6" or "2025-06") or a list
        of them, restricting which monthly files are loaded. Defaults to every
        gps_data_<year>-<month>.csv file found in DATA_DIR.
    """
    if months is None:
        files = sorted(
            p for p in Path(config.DATA_DIR).glob("gps_data_*.csv")
            if _MONTHLY_GPS_DATA_RE.match(p.name)
        )
    else:
        if isinstance(months, str):
            months = [months]
        files = []
        for m in months:
            year, month = m.split("-")
            path = _path(f"gps_data_{int(year)}-{int(month)}.csv")
            if not path.exists():
                raise FileNotFoundError(f"No GPS data file found for month {m!r}: {path}")
            files.append(path)

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
