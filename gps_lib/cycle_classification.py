"""Haul-cycle extraction, phase decomposition, and segment classification
(Sections 4.3 and 4.4)."""
from typing import List

import pandas as pd

from . import zones as zones_mod


def _collapse_consecutive(indices: List[int]) -> List[List[int]]:
    """Group a sorted list of row indices into runs of consecutive integers."""
    if not indices:
        return []
    groups, cur = [], [indices[0]]
    for idx in indices[1:]:
        if idx == cur[-1] + 1:
            cur.append(idx)
        else:
            groups.append(cur)
            cur = [idx]
    groups.append(cur)
    return groups


def extract_cycles(gps_hits_df: pd.DataFrame, load_value: str = "load") -> List[dict]:
    """Split each dump truck's trajectory into cycles: arrival at one
    load-zone visit through arrival at the next.

    gps_hits_df must have zone_load_hit per ping (see zones.assign_zone_hit),
    and is expected to already be restricted to technic_type == 'dump'.
    """
    cycles = []
    for tid, g in gps_hits_df.groupby("tracker_id"):
        g = g.sort_values("get_time").reset_index(drop=True)
        load_idx = g.index[g["zone_load_hit"] == load_value].tolist()
        visits = _collapse_consecutive(load_idx)
        arrivals = [v[0] for v in visits]
        for i in range(len(arrivals) - 1):
            start, end = arrivals[i], arrivals[i + 1]
            seg = g.iloc[start:end + 1].reset_index(drop=True)
            cycles.append({
                "tracker_id": tid,
                "cycle_start": seg.iloc[0]["get_time"],
                "cycle_end": seg.iloc[-1]["get_time"],
                "points": seg,
            })
    return cycles


def decompose_cycle(points: pd.DataFrame, load_value: str = "load", dump_value: str = "unload") -> dict:
    """Split one cycle's points into load-dwell / haul-to-dump / dump-dwell /
    haul-to-load durations (seconds).

    The cycle is assumed to start inside the initial load-zone visit (as
    produced by extract_cycles). dump_dwell_sec sums every dump-zone visit
    within the cycle and n_dump_visits records how many there were, since a
    truck may make multiple partial dump stops per load.
    """
    points = points.reset_index(drop=True)
    t0, t_end = points.iloc[0]["get_time"], points.iloc[-1]["get_time"]

    load_idx = points.index[points["zone_load_hit"] == load_value].tolist()
    load_visits = _collapse_consecutive(load_idx)
    load_visit_end_idx = load_visits[0][-1] if load_visits else 0
    load_dwell_end_time = points.iloc[load_visit_end_idx]["get_time"]
    load_dwell_sec = (load_dwell_end_time - t0).total_seconds()

    dump_idx = points.index[points["zone_load_hit"] == dump_value].tolist()
    dump_visits = _collapse_consecutive(dump_idx)

    if dump_visits:
        dump_dwell_sec = sum(
            (points.iloc[v[-1]]["get_time"] - points.iloc[v[0]]["get_time"]).total_seconds()
            for v in dump_visits
        )
        first_dump_start = points.iloc[dump_visits[0][0]]["get_time"]
        last_dump_end = points.iloc[dump_visits[-1][-1]]["get_time"]
        haul_to_dump_sec = (first_dump_start - load_dwell_end_time).total_seconds()
        haul_to_load_sec = (t_end - last_dump_end).total_seconds()
    else:
        dump_dwell_sec = None
        haul_to_dump_sec = None
        haul_to_load_sec = (t_end - load_dwell_end_time).total_seconds()

    return {
        "load_dwell_sec": load_dwell_sec,
        "haul_to_dump_sec": haul_to_dump_sec,
        "dump_dwell_sec": dump_dwell_sec,
        "haul_to_load_sec": haul_to_load_sec,
        "total_sec": (t_end - t0).total_seconds(),
        "n_dump_visits": len(dump_visits),
    }


def cycles_to_dataframe(cycles: List[dict]) -> pd.DataFrame:
    """Flatten extract_cycles() output + per-cycle phase decomposition into one row per cycle."""
    rows = []
    for i, c in enumerate(cycles):
        rows.append({
            "cycle_idx": i,
            "tracker_id": c["tracker_id"],
            "cycle_start": c["cycle_start"],
            "cycle_end": c["cycle_end"],
            **decompose_cycle(c["points"]),
        })
    return pd.DataFrame(rows)


def classify_segments(gps_hits_df: pd.DataFrame, zones_gdf, speed_col: str = "speed",
                       speed_threshold: float = 2.0, queue_buffer_m: float = 50.0) -> pd.DataFrame:
    """Tag every ping as transit / operating / queuing / unplanned_idle (Section 4.4).

    gps_hits_df must already have zone_id_hit from zones.assign_zone_hit.
    - operating: stopped, inside a zone polygon.
    - queuing: stopped, outside any zone, but within queue_buffer_m of a
      load-zone polygon (waiting for the shovel).
    - unplanned_idle: stopped, outside all zones, not near a load zone.
    - transit: everything else (moving).
    """
    df = gps_hits_df.copy()
    is_stopped = df[speed_col] < speed_threshold
    inside_zone = df["zone_id_hit"].notna()

    load_zones = zones_gdf[zones_gdf["zone_load_type"] == "load"].copy()
    load_zones["geometry"] = load_zones.geometry.buffer(queue_buffer_m / 111320.0)

    candidates = df[is_stopped & ~inside_zone]
    if not candidates.empty:
        near = zones_mod.assign_zone_hit(candidates, load_zones)["zone_id_hit"].notna()
        near_load_idx = candidates.index[near.values]
    else:
        near_load_idx = pd.Index([])

    df["state"] = "transit"
    df.loc[is_stopped & inside_zone, "state"] = "operating"
    df.loc[near_load_idx, "state"] = "queuing"
    remaining_idle = is_stopped & ~inside_zone & ~df.index.isin(near_load_idx)
    df.loc[remaining_idle, "state"] = "unplanned_idle"
    return df


def state_time_breakdown(df: pd.DataFrame, state_col: str = "state", dt_col: str = "dt") -> pd.Series:
    """Fraction of total fleet-time spent in each state, weighted by `dt`
    (seconds since the previous ping; see preprocess.add_motion_features).
    """
    valid = df[df[dt_col].notna() & (df[dt_col] > 0)]
    total = valid[dt_col].sum()
    return (valid.groupby(state_col)[dt_col].sum() / total).sort_values(ascending=False)
