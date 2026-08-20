"""Heavy one-time preprocessing for the GPS Fleet Ops Agent.

Turns raw gps_data_<year>-<month>.csv pings into small, pre-aggregated CSVs
under data/agent_data/ so gps_fleet_agent.ipynb only ever reads a handful of
rows per question instead of running geopandas/DBSCAN over millions of pings
at answer time (see fleet_agent/gps_fleet_agent.ipynb for the crash that motivated
this split).

Scoped to the BN sub-fleet and BN zones only for now (drop_other on trackers
and zones). Run directly:

    python fleet_agent/preprocessing.py

Output layout (all under data/agent_data/):
- tracker_list_bn.csv     BN tracker inventory (technic_type, technic_m_type)
- zone_diameter_bn.csv    BN zone size sanity stats
- daily_<year>-<month>.csv   one row per (date, tracker_id) that month — cycle
                              KPIs + fleet-time breakdown + DBSCAN idle share.
                              tracker_id="ALL" is the fleet-wide row for that
                              date; every other tracker_id is one BN truck.
- routes_<year>-<month>.csv  one row per load/unload zone pair that month
- zone_qa_<year>-<month>.csv one row per BN zone that month (stopped-ping count)
- monthly_<year>.csv         one row per (month, tracker_id) — daily_*.csv
                              rolled up per truck (median/p90 columns are a
                              weighted average of daily medians/p90s, not
                              recomputed from raw cycles, so treat them as
                              approximate)
"""
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from gps_lib import io_utils, config, classify, preprocess, zones as zones_mod
from gps_lib import cycles as cycles_mod, cycle_classification, stops as stops_mod

SPEED_THRESHOLD_KMH = 3.0  # below this, a truck counts as "stopped" (see gps_fleet_agent.ipynb)
AGENT_DATA_DIR = Path(config.DATA_DIR) / "agent_data"
_MONTH_FILE_RE = re.compile(r"^gps_data_(\d{4})-(\d{1,2})\.csv$")

ONLY_MONTH: Optional[str] = None  # dev filter: build_all() processes just this month.
                                       # Comment this out (or set to None) to process every
                                       # gps_data_<year>-<month>.csv found in data/.


def _norm_month(month: str) -> str:
    year, mon = month.split("-")
    return f"{int(year)}-{int(mon):02d}"


def load_bn_reference():
    """Tracker list + zone geodataframe, filtered down to the BN sub-fleet/zones."""
    tracker_list = classify.classify_technic_type(io_utils.load_tracker_list())
    tracker_list = classify.classify_technic_material_type(tracker_list)
    tracker_list = tracker_list[tracker_list["technic_m_type"] == "bn"].reset_index(drop=True)

    zone_list = classify.classify_zones(io_utils.load_zone_list(), drop_other=True)
    zone_list = zone_list[zone_list["zone_material_type"] == "bn"]
    zone_detail = io_utils.load_zone_detail()
    zone_gdf = zones_mod.build_zone_geodataframe(zone_detail, zone_list)
    # build_zone_geodataframe builds a polygon for every zone_id in zone_detail
    # (not just BN ones) then left-merges metadata, so non-BN zones survive
    # with NaN metadata unless filtered out here too.
    zone_gdf = zone_gdf[zone_gdf["zone_material_type"] == "bn"].reset_index(drop=True)
    return tracker_list, zone_gdf


def process_month(month: str, tracker_list: pd.DataFrame, zone_gdf):
    """Clean + classify one month's raw pings, restricted to BN trucks/zones.

    Returns (pings_df, cycles_df); both empty if the month has no BN activity.
    Pings that fall inside a real but non-BN zone are treated as zone-less
    (no zone polygon to match against) — an accepted approximation while this
    pipeline is scoped to BN only.
    """
    raw = io_utils.load_gps_data(month)
    df = preprocess.clean_gps_points(raw)
    df = preprocess.attach_technic_info(df, tracker_list)  # inner join drops non-BN trucks
    if df.empty:
        return df, pd.DataFrame()

    df = preprocess.add_motion_features(df)
    df = cycles_mod.assign_zone_hit_fast(df, zone_gdf)
    df = cycle_classification.classify_segments(df, zone_gdf, speed_col="speed_kmh",
                                                  speed_threshold=SPEED_THRESHOLD_KMH)

    dump = df[df["technic_type"] == "dump"]
    cycles_df = cycles_mod.extract_cycles(dump) if not dump.empty else pd.DataFrame()
    return df, cycles_df


_DAILY_COLS = ["date", "tracker_id", "truck", "total_dt_hr", "pct_transit", "pct_operating",
               "pct_queuing", "pct_unplanned_idle", "dbscan_unplanned_idle_share", "n_cycles",
               "cycle_mean_min", "cycle_median_min", "cycle_p90_min", "cycle_total_h",
               "haul_mean_min", "dump_mean_min", "return_mean_min", "cycle_km_mean", "total_km"]


def bn_dbscan_eps_m(zone_gdf) -> float:
    """DBSCAN eps sized to the BN zones themselves — same rule of thumb as
    notebooks/analysis/data_qa.ipynb (roughly half the smallest real zone's
    diameter). The gps_lib default (30m) was tuned for the full zone set and
    is far tighter than these BN zones (smallest ~430m across), which made
    almost every real stop cluster get thrown out as DBSCAN "noise" and
    silently zeroed out dbscan_unplanned_idle_share.
    """
    diam = zones_mod.zone_diameter_stats(zone_gdf)
    return round(float(diam["diameter_m"].quantile(0.1)) / 2, 1)


def _summary_row(date, tracker_id, truck, day_pings: pd.DataFrame, day_cycles: pd.DataFrame,
                  zone_gdf, eps_m: float) -> dict:
    valid = day_pings[day_pings["dt"].notna() & (day_pings["dt"] > 0)]
    total_dt_hr = round(valid["dt"].sum() / 3600, 2) if not valid.empty else 0.0
    breakdown = (cycle_classification.state_time_breakdown(day_pings) * 100).round(1) if not valid.empty else pd.Series(dtype=float)

    stop_df = stops_mod.filter_stop_pings(day_pings, speed_col="speed_kmh", speed_threshold=SPEED_THRESHOLD_KMH)
    dbscan_share = np.nan
    if not stop_df.empty:
        labeled = stops_mod.cluster_and_label_stops(stop_df, zone_gdf, eps_m=eps_m)
        dbscan_share = stops_mod.unplanned_idle_share(labeled)

    stats = cycles_mod.cycle_stats(day_cycles) if len(day_cycles) else pd.Series(dtype=float)

    return {
        "date": date,
        "tracker_id": tracker_id,
        "truck": truck,
        "total_dt_hr": total_dt_hr,
        "pct_transit": breakdown.get("transit", 0.0),
        "pct_operating": breakdown.get("operating", 0.0),
        "pct_queuing": breakdown.get("queuing", 0.0),
        "pct_unplanned_idle": breakdown.get("unplanned_idle", 0.0),
        "dbscan_unplanned_idle_share": round(dbscan_share, 3) if pd.notna(dbscan_share) else np.nan,
        "n_cycles": int(stats.get("cycles", 0)),
        "cycle_mean_min": stats.get("cycle_mean_min", np.nan),
        "cycle_median_min": stats.get("cycle_median_min", np.nan),
        "cycle_p90_min": stats.get("cycle_p90_min", np.nan),
        "cycle_total_h": stats.get("cycle_total_h", np.nan),
        "haul_mean_min": stats.get("haul_mean_min", np.nan),
        "dump_mean_min": stats.get("dump_mean_min", np.nan),
        "return_mean_min": stats.get("return_mean_min", np.nan),
        "cycle_km_mean": stats.get("cycle_km_mean", np.nan),
        "total_km": stats.get("total_km", np.nan),
    }


def daily_summary(pings_df: pd.DataFrame, cycles_df: pd.DataFrame, zone_gdf, eps_m: float) -> pd.DataFrame:
    """One row per (date, tracker_id): fleet-time state breakdown + cycle KPIs + DBSCAN idle share.

    tracker_id="ALL" is the fleet-wide row for that date; every other
    tracker_id is one BN truck's own numbers for that date. eps_m is the
    DBSCAN stop-cluster radius — see bn_dbscan_eps_m().
    """
    if pings_df.empty:
        return pd.DataFrame(columns=_DAILY_COLS)

    rows = []
    for day, day_pings in pings_df.groupby("date"):
        day_cycles = cycles_df[cycles_df["date"] == day] if not cycles_df.empty else cycles_df
        rows.append(_summary_row(day, "ALL", "ALL", day_pings, day_cycles, zone_gdf, eps_m))

        for tracker_id, truck_pings in day_pings.groupby("tracker_id"):
            truck_cycles = day_cycles[day_cycles["tracker_id"] == tracker_id] if len(day_cycles) else day_cycles
            truck_label = truck_pings["label"].iloc[0]
            rows.append(_summary_row(day, str(tracker_id), truck_label, truck_pings, truck_cycles, zone_gdf, eps_m))

    daily = pd.DataFrame(rows, columns=_DAILY_COLS)
    daily["_fleet_first"] = (daily["tracker_id"] != "ALL").astype(int)
    daily = daily.sort_values(["date", "_fleet_first", "tracker_id"]).drop(columns="_fleet_first")
    return daily.reset_index(drop=True)


def route_summary(cycles_df: pd.DataFrame, zone_gdf) -> pd.DataFrame:
    """Load/unload route share table for the month (BN region only)."""
    if cycles_df.empty:
        return pd.DataFrame()
    _full, main = cycles_mod.route_breakdown(cycles_df, zone_gdf, region="bn")
    return main


def zone_qa_summary(pings_df: pd.DataFrame, zone_gdf) -> pd.DataFrame:
    """Stopped-ping count per BN zone for the month — flags zones with no recorded activity."""
    if pings_df.empty:
        return pd.DataFrame()
    return zones_mod.zone_ping_density(pings_df, zone_gdf, speed_col="speed_kmh",
                                        speed_threshold=SPEED_THRESHOLD_KMH)


def build_month_csvs(month: str, tracker_list: pd.DataFrame, zone_gdf, out_dir: Optional[Path] = None,
                      eps_m: Optional[float] = None) -> None:
    out_dir = Path(out_dir or AGENT_DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    month = _norm_month(month)
    eps_m = eps_m if eps_m is not None else bn_dbscan_eps_m(zone_gdf)

    pings_df, cycles_df = process_month(month, tracker_list, zone_gdf)

    daily = daily_summary(pings_df, cycles_df, zone_gdf, eps_m)
    daily.to_csv(out_dir / f"daily_{month}.csv", index=False)

    routes = route_summary(cycles_df, zone_gdf)
    routes.to_csv(out_dir / f"routes_{month}.csv", index=False)

    zone_qa = zone_qa_summary(pings_df, zone_gdf)
    zone_qa.to_csv(out_dir / f"zone_qa_{month}.csv", index=False)

    print(f"{month}: daily={len(daily)} days, routes={len(routes)}, zone_qa={len(zone_qa)} zones")


def build_yearly_csv(year: str, out_dir: Optional[Path] = None) -> None:
    """Roll daily_<year>-*.csv files up into one monthly_<year>.csv (one row per (month, tracker_id))."""
    out_dir = Path(out_dir or AGENT_DATA_DIR)
    daily_files = sorted(out_dir.glob(f"daily_{year}-*.csv"))
    if not daily_files:
        print(f"No daily_{year}-*.csv files found in {out_dir} yet — run build_month_csvs first.")
        return

    def wavg(g: pd.DataFrame, col: str, weight: pd.Series):
        """Weighted average, ignoring rows where col is NaN (e.g. a zero-cycle day).

        np.average propagates NaN even when that row's weight is 0, so a
        single zero-cycle day would otherwise wipe out a truck's entire
        monthly cycle_mean_min/median_min/p90_min to NaN.
        """
        valid = g[col].notna()
        w = weight[valid]
        return float(np.average(g.loc[valid, col], weights=w)) if w.notna().any() and w.sum() > 0 else np.nan

    rows = []
    for f in daily_files:
        month = f.stem.replace("daily_", "")
        daily = pd.read_csv(f, dtype={"tracker_id": str})
        if daily.empty:
            continue

        for tracker_id, g in daily.groupby("tracker_id"):
            w_cycles = g["n_cycles"].fillna(0)
            w_hours = g["total_dt_hr"].fillna(0)
            rows.append({
                "month": month,
                "tracker_id": tracker_id,
                "truck": g["truck"].iloc[0],
                "n_days": len(g),
                "total_dt_hr": round(g["total_dt_hr"].sum(), 1),
                "pct_transit": round(wavg(g, "pct_transit", w_hours), 1),
                "pct_operating": round(wavg(g, "pct_operating", w_hours), 1),
                "pct_queuing": round(wavg(g, "pct_queuing", w_hours), 1),
                "pct_unplanned_idle": round(wavg(g, "pct_unplanned_idle", w_hours), 1),
                "dbscan_unplanned_idle_share": round(wavg(g, "dbscan_unplanned_idle_share", w_hours), 3),
                "n_cycles": int(g["n_cycles"].sum()),
                "cycle_mean_min": round(wavg(g, "cycle_mean_min", w_cycles), 1),
                "cycle_median_min": round(wavg(g, "cycle_median_min", w_cycles), 1),
                "cycle_p90_min": round(wavg(g, "cycle_p90_min", w_cycles), 1),
                "cycle_total_h": round(g["cycle_total_h"].sum(), 1),
                "haul_mean_min": round(wavg(g, "haul_mean_min", w_cycles), 1),
                "dump_mean_min": round(wavg(g, "dump_mean_min", w_cycles), 1),
                "return_mean_min": round(wavg(g, "return_mean_min", w_cycles), 1),
                "cycle_km_mean": round(wavg(g, "cycle_km_mean", w_cycles), 2),
                "total_km": round(g["total_km"].sum(), 0),
            })

    monthly = pd.DataFrame(rows)
    monthly["_fleet_first"] = (monthly["tracker_id"] != "ALL").astype(int)
    monthly = monthly.sort_values(["month", "_fleet_first", "tracker_id"]).drop(columns="_fleet_first")
    monthly = monthly.reset_index(drop=True)
    monthly.to_csv(out_dir / f"monthly_{year}.csv", index=False)
    print(f"{year}: wrote monthly rollup ({len(monthly)} rows across "
          f"{monthly['month'].nunique()} months) -> monthly_{year}.csv")


def build_all(out_dir: Optional[Path] = None) -> None:
    """Discover every gps_data_<year>-<month>.csv in data/ and build all agent CSVs."""
    out_dir = Path(out_dir or AGENT_DATA_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    tracker_list, zone_gdf = load_bn_reference()
    tracker_list.to_csv(out_dir / "tracker_list_bn.csv", index=False)
    zones_mod.zone_diameter_stats(zone_gdf).to_csv(out_dir / "zone_diameter_bn.csv", index=False)
    eps_m = bn_dbscan_eps_m(zone_gdf)
    print(f"BN reference: {len(tracker_list)} trackers, {len(zone_gdf)} zones, DBSCAN eps={eps_m}m")

    months = sorted(
        f"{int(m.group(1))}-{int(m.group(2)):02d}"
        for p in Path(config.DATA_DIR).glob("gps_data_*.csv")
        if (m := _MONTH_FILE_RE.match(p.name))
    )
    if not months:
        print(f"No gps_data_<year>-<month>.csv files found in {config.DATA_DIR}.")
        return

    if ONLY_MONTH:
        only = _norm_month(ONLY_MONTH)
        months = [m for m in months if m == only]
        if not months:
            print(f"ONLY_MONTH={only!r} set but no matching gps_data_{only}.csv found in {config.DATA_DIR}.")
            return

    for month in months:
        build_month_csvs(month, tracker_list, zone_gdf, out_dir, eps_m)

    for year in sorted({m.split("-")[0] for m in months}):
        build_yearly_csv(year, out_dir)


if __name__ == "__main__":
    build_all()
