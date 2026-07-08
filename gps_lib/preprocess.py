"""Cleaning pipeline for raw GPS pings."""
import pandas as pd

from . import routes


def clean_gps_points(track_points_df: pd.DataFrame, round_n: int = 4,
                      dedup_cols=("lat", "lng", "date", "hour", "tracker_id")) -> pd.DataFrame:
    """Dedupe raw pings, parse timestamps, and collapse near-duplicate points.

    round_n: decimal places to round lat/lng to before the second dedup pass.
        4 dp ~= 11m precision, 5 dp ~= 1.1m, 6 dp ~= 0.11m.
    """
    df = track_points_df.drop_duplicates().copy()
    df["get_time"] = pd.to_datetime(df["get_time"], errors="coerce")
    if "tracker_id" in df.columns:
        df = df.sort_values(["tracker_id", "get_time"]).reset_index(drop=True)
    df["date"] = df["get_time"].dt.date
    df["hour"] = df["get_time"].dt.hour

    if "lat" in df.columns:
        df["lat"] = df["lat"].round(round_n)
    if "lng" in df.columns:
        df["lng"] = df["lng"].round(round_n)

    cols = [c for c in dedup_cols if c in df.columns]
    return df.drop_duplicates(subset=cols, keep="first")


def add_motion_features(df: pd.DataFrame, tracker_col: str = "tracker_id",
                         time_col: str = "get_time", max_speed_kmh: float = 120.0) -> pd.DataFrame:
    """Per-ping `dt` (sec since previous ping), `dist` (m, haversine), and
    `speed_kmh` since the previous ping for the same tracker.

    Flags pings implying speed above max_speed_kmh as `implausible_jump`
    (likely a GPS glitch). A tracker's first ping always has dt/dist/speed
    NaN and implausible_jump False.
    """
    df = df.sort_values([tracker_col, time_col]).copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")

    grp = df.groupby(tracker_col)
    prev_lat = grp["lat"].shift()
    prev_lng = grp["lng"].shift()
    prev_time = grp[time_col].shift()

    df["dt"] = (df[time_col] - prev_time).dt.total_seconds()
    df["dist"] = routes.haversine(prev_lng, prev_lat, df["lng"], df["lat"])
    df["speed_kmh"] = (df["dist"] / df["dt"]) * 3.6
    df["implausible_jump"] = df["speed_kmh"] > max_speed_kmh
    return df


def filter_by_time(df: pd.DataFrame, start, end, time_col: str = "get_time") -> pd.DataFrame:
    """Keep rows with start <= time_col <= end."""
    start, end = pd.to_datetime(start), pd.to_datetime(end)
    times = pd.to_datetime(df[time_col], errors="coerce")
    return df[(times >= start) & (times <= end)]


def attach_technic_info(track_points_df: pd.DataFrame, tracker_list_df: pd.DataFrame) -> pd.DataFrame:
    """Join GPS pings to tracker metadata (technic_type, technic_m_type, label, ...)."""
    return pd.merge(
        track_points_df, tracker_list_df,
        left_on="tracker_id", right_on="id", how="inner",
    )
