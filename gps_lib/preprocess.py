"""Cleaning pipeline for raw GPS pings."""
import pandas as pd


def clean_gps_points(track_points_df: pd.DataFrame, round_n: int = 4,
                      dedup_cols=("lat", "lng", "date", "hour", "tracker_id")) -> pd.DataFrame:
    """Dedupe raw pings, parse timestamps, and collapse near-duplicate points.

    round_n: decimal places to round lat/lng to before the second dedup pass.
        4 dp ~= 11m precision, 5 dp ~= 1.1m, 6 dp ~= 0.11m.
    """
    df = track_points_df.drop_duplicates().copy()
    df["get_time"] = pd.to_datetime(df["get_time"], errors="coerce")
    df["date"] = df["get_time"].dt.date
    df["hour"] = df["get_time"].dt.hour

    if "lat" in df.columns:
        df["lat"] = df["lat"].round(round_n)
    if "lng" in df.columns:
        df["lng"] = df["lng"].round(round_n)

    cols = [c for c in dedup_cols if c in df.columns]
    return df.drop_duplicates(subset=cols, keep="first")


def filter_by_time(df: pd.DataFrame, start, end, time_col: str = "get_time") -> pd.DataFrame:
    """Keep rows with start <= time_col <= end."""
    start, end = pd.to_datetime(start), pd.to_datetime(end)
    return df[(df[time_col] >= start) & (df[time_col] <= end)]


def attach_technic_info(track_points_df: pd.DataFrame, tracker_list_df: pd.DataFrame) -> pd.DataFrame:
    """Join GPS pings to tracker metadata (technic_type, technic_m_type, label, ...)."""
    return pd.merge(
        track_points_df, tracker_list_df,
        left_on="tracker_id", right_on="id", how="inner",
    )
