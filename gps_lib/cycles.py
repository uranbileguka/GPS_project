"""Full round-trip haul-cycle extraction, metrics, and plots.

Extends routes.py (which extracts one-way load->unload routes) with the
**round trip**: depart a LOAD zone -> reach an UNLOAD zone -> return to a LOAD
zone = one cycle, split into haul / dump / return legs with per-leg distance.

Region = truck fleet (technic_m_type: 'bn' if label contains BN, else 'other').
Reuses classify / preprocess / zones for the upstream steps; this module only
adds the cycle layer and its visualizations.
"""
from typing import Optional

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Point
except ImportError:  # geopandas/shapely only needed for the fast zone-hit join
    gpd = None

import matplotlib.pyplot as plt

MAX_CYCLE_HOURS = 6  # drop cycles longer than this (tracker offline / shift gap)


# --------------------------------------------------------------------------- #
# 1. Fast zone-hit assignment (sjoin) — same output columns as
#    zones.assign_zone_hit, but vectorized for millions of points.
# --------------------------------------------------------------------------- #
def assign_zone_hit_fast(gps_df: pd.DataFrame, zones_gdf) -> pd.DataFrame:
    """Tag each ping with the zone it falls in via a spatial join.

    Returns a copy of gps_df with zone_id_hit / zone_mat_hit / zone_load_hit
    columns (identical schema to zones.assign_zone_hit, ~100x faster).
    """
    if gpd is None:
        raise ImportError("geopandas and shapely are required for assign_zone_hit_fast")
    pts = gpd.GeoDataFrame(
        gps_df.copy(), geometry=gpd.points_from_xy(gps_df["lng"], gps_df["lat"]),
        crs="EPSG:4326",
    )
    hit = gpd.sjoin(
        pts, zones_gdf[["geometry", "zone_id", "zone_material_type", "zone_load_type"]],
        predicate="within", how="left",
    )
    hit = hit[~hit.index.duplicated(keep="first")]
    out = pd.DataFrame(hit.drop(columns="geometry")).rename(columns={
        "zone_id": "zone_id_hit",
        "zone_material_type": "zone_mat_hit",
        "zone_load_type": "zone_load_hit",
    })
    if "index_right" in out.columns:
        out = out.drop(columns="index_right")
    return out


# --------------------------------------------------------------------------- #
# 2. Cycle extraction (load -> unload -> load) with timing + distance
# --------------------------------------------------------------------------- #
def _hav_m(lon1, lat1, lon2, lat2):
    """Vectorized haversine in metres."""
    R = 6371000.0
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    d = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(d))


def extract_cycles(gps_hits_df: pd.DataFrame, max_cycle_hours: float = MAX_CYCLE_HOURS) -> pd.DataFrame:
    """Extract full round-trip cycles per tracker.

    gps_hits_df must have: tracker_id, get_time, lat, lng, label, technic_m_type,
    and the zone_*_hit columns from assign_zone_hit_fast / zones.assign_zone_hit.

    One cycle = depart a load zone -> reach an unload zone -> return to a load
    zone. Each row carries the four phase timestamps, the haul/dump/return/cycle
    durations (seconds), and the haul/return/cycle road distances (km, summed
    along the actual GPS track).
    """
    rows = []
    for tid, g in gps_hits_df.groupby("tracker_id"):
        g = g.sort_values("get_time")
        zid = g["zone_id_hit"].values
        lt = g["zone_load_hit"].values
        mat = g["zone_mat_hit"].values
        t = g["get_time"].values
        la = g["lat"].values.astype(float)
        lo = g["lng"].values.astype(float)
        info = g.iloc[0]

        # cumulative road distance (km) along this tracker's points
        step = np.zeros(len(g))
        if len(g) > 1:
            step[1:] = _hav_m(lo[:-1], la[:-1], lo[1:], la[1:])
        cum = np.cumsum(step) / 1000.0

        def pkm(ta, tb):
            ia = min(int(np.searchsorted(t, ta)), len(cum) - 1)
            ib = min(int(np.searchsorted(t, tb)), len(cum) - 1)
            return round(max(0.0, cum[ib] - cum[ia]), 3)

        # collapse consecutive in-zone points into visits
        visits, i, n = [], 0, len(g)
        while i < n:
            if pd.isna(zid[i]):
                i += 1
                continue
            j = i
            while j + 1 < n and zid[j + 1] == zid[i]:
                j += 1
            visits.append((lt[i], zid[i], mat[i], t[i], t[j]))
            i = j + 1

        # state machine: load -> unload -> load
        pend_load = pend_unload = None
        for vtype, vz, vm, arr, dep in visits:
            if vtype == "load":
                if pend_load is not None and pend_unload is not None:
                    dl, dz, dm = pend_load
                    ua, ud, uz, um = pend_unload
                    cyc = (arr - dl) / np.timedelta64(1, "s")
                    if 0 < cyc <= max_cycle_hours * 3600:
                        rows.append(dict(
                            tracker_id=tid, region=info["technic_m_type"], truck=info["label"],
                            load_zone=int(dz), load_mat=dm, unload_zone=int(uz), unload_mat=um,
                            depart_load=pd.Timestamp(dl), arrive_unload=pd.Timestamp(ua),
                            depart_unload=pd.Timestamp(ud), arrive_load=pd.Timestamp(arr),
                            haul_s=(ua - dl) / np.timedelta64(1, "s"),
                            dump_s=(ud - ua) / np.timedelta64(1, "s"),
                            return_s=(arr - ud) / np.timedelta64(1, "s"), cycle_s=cyc,
                            haul_km=pkm(dl, ua), return_km=pkm(ud, arr), cycle_km=pkm(dl, arr),
                        ))
                    pend_load, pend_unload = (dep, vz, vm), None
                else:
                    pend_load = (dep, vz, vm)
            else:  # unload
                if pend_load is not None:
                    pend_unload = (arr, dep, vz, vm) if pend_unload is None else (pend_unload[0], dep, pend_unload[2], pend_unload[3])

    cycles = pd.DataFrame(rows)
    if not cycles.empty:
        cycles["date"] = cycles["depart_load"].dt.date
        cycles["week"] = cycles["depart_load"].dt.to_period("W").astype(str)
        cycles["month"] = cycles["depart_load"].dt.to_period("M").astype(str)
    return cycles


# --------------------------------------------------------------------------- #
# 3. Aggregation
# --------------------------------------------------------------------------- #
def cycle_stats(g: pd.DataFrame) -> pd.Series:
    """Count + duration + distance summary for one group of cycles."""
    return pd.Series({
        "cycles": len(g),
        "cycle_mean_min": round(g.cycle_s.mean() / 60, 1),
        "cycle_median_min": round(g.cycle_s.median() / 60, 1),
        "cycle_p90_min": round(g.cycle_s.quantile(0.9) / 60, 1),
        "cycle_total_h": round(g.cycle_s.sum() / 3600, 1),
        "haul_mean_min": round(g.haul_s.mean() / 60, 1),
        "dump_mean_min": round(g.dump_s.mean() / 60, 1),
        "return_mean_min": round(g.return_s.mean() / 60, 1),
        "cycle_km_mean": round(g.cycle_km.mean(), 2),
        "cycle_km_median": round(g.cycle_km.median(), 2),
        "haul_km_mean": round(g.haul_km.mean(), 2),
        "total_km": round(g.cycle_km.sum(), 0),
    })


def summarize_cycles(cycles: pd.DataFrame, by="region") -> pd.DataFrame:
    """Group cycles by one or more keys and apply cycle_stats."""
    keys = [by] if isinstance(by, str) else list(by)
    return cycles.groupby(keys).apply(cycle_stats, include_groups=False)


def route_breakdown(cycles: pd.DataFrame, zones_gdf, region: str, min_share: float = 0.2):
    """Per-route (load->unload pair) table for one region, with measured distance.

    Returns (full_table, main_table). main_table keeps routes with >= min_share %.
    """
    sub = cycles[cycles.region == region]
    lbl = {int(z.zone_id): str(z["label"]).strip() for _, z in zones_gdf.iterrows()}
    cent = {int(z.zone_id): (z.geometry.centroid.x, z.geometry.centroid.y) for _, z in zones_gdf.iterrows()}
    g = (sub.groupby(["load_zone", "unload_zone", "load_mat", "unload_mat"])
         .agg(cycles=("cycle_s", "size"),
              haul_km=("haul_km", "mean"), cycle_km=("cycle_km", "mean"),
              haul_min=("haul_s", lambda x: round(x.mean() / 60, 1)),
              cycle_min=("cycle_s", lambda x: round(x.mean() / 60, 1)))
         .reset_index())
    g["straight_km"] = [
        round(_hav_m(*cent[a], *cent[b]) / 1000, 2) if a in cent and b in cent else np.nan
        for a, b in zip(g.load_zone, g.unload_zone)
    ]
    g["haul_km"] = g.haul_km.round(2)
    g["cycle_km"] = g.cycle_km.round(2)
    g["load"] = g.load_zone.map(lbl)
    g["unload"] = g.unload_zone.map(lbl)
    g["share_pct"] = (g.cycles / len(sub) * 100).round(1)
    g = g.sort_values("cycles", ascending=False)
    main = g[g.share_pct >= min_share]
    return g, main


# --------------------------------------------------------------------------- #
# 4. Plots
# --------------------------------------------------------------------------- #
_LOAD_C, _UNLOAD_C = "#2ca02c", "#d62728"


def _region_zones(zones_gdf, region: str):
    z = zones_gdf.copy()
    z["region"] = np.where(z["zone_material_type"] == "bn", "bn", "other")
    return z[z.region == region]


def plot_zones_loadunload(zones_gdf, region: str, figsize=None):
    """Numbered load (green) / unload (red, hatched) map for one region."""
    def panel(ax, sub, title):
        sub = sub.reset_index(drop=True)
        for k, z in sub.iterrows():
            c = _LOAD_C if z.zone_load_type == "load" else _UNLOAD_C
            xs, ys = z.geometry.exterior.xy
            ax.fill(xs, ys, facecolor=c, alpha=0.35, edgecolor=c, lw=2,
                    hatch=None if z.zone_load_type == "load" else "///")
            ax.annotate(str(k + 1), (z.geometry.centroid.x, z.geometry.centroid.y),
                        fontsize=11, weight="bold", ha="center", va="center",
                        color="white", bbox=dict(boxstyle="circle", fc=c, ec="white"))
        txt = "\n".join(
            f"{k+1}. [{'LOAD ' if r.zone_load_type=='load' else 'UNLOAD'}] {str(r.label).strip()} ({r.zone_id})"
            for k, r in sub.iterrows())
        ax.text(0.02, 0.98, txt, transform=ax.transAxes, fontsize=8.5, family="monospace",
                va="top", bbox=dict(boxstyle="round", fc="white", ec="gray", alpha=0.9))
        ax.set_title(title); ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        ax.grid(alpha=0.3); ax.set_aspect("equal", "datalim")

    zr = _region_zones(zones_gdf, region)
    if region == "bn":
        fig, axs = plt.subplots(1, 2, figsize=figsize or (15, 6))
        panel(axs[0], zr[zr.zone_load_type == "load"], "BN — LOAD area (west pit)")
        panel(axs[1], zr[zr.zone_load_type == "unload"], "BN — UNLOAD area (east pile)")
    else:
        fig, ax = plt.subplots(figsize=figsize or (11, 9))
        panel(ax, zr, "OTHER region — LOAD (green) vs UNLOAD (red)")
    fig.tight_layout()
    return fig


def plot_truck_cycles(cycles: pd.DataFrame, gps_hits: pd.DataFrame, zones_gdf,
                      region: str, truck_id=None, max_cycles: int = 6, figsize=(11, 9)):
    """Spatial route of one truck's first N cycles (one region)."""
    cc = cycles[cycles.region == region]
    if truck_id is None:
        truck_id = cc.tracker_id.value_counts().idxmax()
    total = int((cc.tracker_id == truck_id).sum())
    cc = cc[cc.tracker_id == truck_id].sort_values("depart_load").head(max_cycles)
    pts = gps_hits[gps_hits.tracker_id == truck_id].sort_values("get_time")
    fig, ax = plt.subplots(figsize=figsize)
    for _, z in _region_zones(zones_gdf, region).iterrows():
        xs, ys = z.geometry.exterior.xy
        c = _LOAD_C if z.zone_load_type == "load" else _UNLOAD_C
        ax.plot(xs, ys, color=c, lw=1.5, ls="-" if z.zone_load_type == "load" else "--")
        ax.fill(xs, ys, color=c, alpha=0.15, hatch=None if z.zone_load_type == "load" else "///")
        ax.annotate(str(z["label"]).strip(), (z.geometry.centroid.x, z.geometry.centroid.y),
                    fontsize=7, color=c, ha="center",
                    bbox=dict(boxstyle="round", fc="white", ec=c, alpha=0.7))
    cmap = plt.cm.viridis(np.linspace(0, 1, max(len(cc), 1)))
    for k, (_, cy) in enumerate(cc.iterrows()):
        seg = pts[(pts.get_time >= cy.depart_load) & (pts.get_time <= cy.arrive_load)]
        ax.plot(seg.lng, seg.lat, "-o", color=cmap[k], ms=3, lw=1.6, alpha=0.85,
                label=f"cycle {k+1}: {cy.cycle_s/60:.0f} min ({int(cy.load_zone)}->{int(cy.unload_zone)})")
    truck = cc.truck.iloc[0] if len(cc) else truck_id
    ax.set_title(f"{region.upper()} — {truck}: {len(cc)} of {total} cycles")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.legend(fontsize=8)
    ax.axis("equal"); ax.grid(alpha=0.3); fig.tight_layout()
    return fig, truck_id


def plot_truck_timeline(cycles: pd.DataFrame, region: str, truck_id, day=None, max_cycles: int = 18):
    """Gantt-style time-line of one truck's cycles on its busiest day."""
    cc = cycles[(cycles.region == region) & (cycles.tracker_id == truck_id)].sort_values("depart_load")
    if day is None:
        day = cc["date"].mode().iloc[0]
    full = cc[cc["date"] == day].reset_index(drop=True)
    cc = full.head(max_cycles)
    fig, ax = plt.subplots(figsize=(13, max(3, 0.32 * len(cc) + 1)))
    base = pd.Timestamp(day)

    def h(ts):
        return (pd.Timestamp(ts) - base) / np.timedelta64(1, "h")

    for k, r in cc.iterrows():
        ax.barh(k, h(r.arrive_unload) - h(r.depart_load), left=h(r.depart_load),
                color="#1f77b4", height=0.7, label="haul (loaded)" if k == 0 else "")
        ax.barh(k, h(r.depart_unload) - h(r.arrive_unload), left=h(r.arrive_unload),
                color="#d62728", height=0.7, label="dump" if k == 0 else "")
        ax.barh(k, h(r.arrive_load) - h(r.depart_unload), left=h(r.depart_unload),
                color="#2ca02c", height=0.7, label="return (empty)" if k == 0 else "")
        ax.text(h(r.depart_load) - 0.05, k, f"{r.cycle_s/60:.0f}m", ha="right", va="center", fontsize=7)
    ax.set_yticks(range(len(cc))); ax.set_yticklabels([f"#{i+1}" for i in range(len(cc))])
    ax.invert_yaxis(); ax.set_xlabel(f"hour of {day}")
    ax.set_title(f"{region.upper()} — {full.truck.iloc[0]}: first {len(cc)} of {len(full)} cycles on {day}")
    ax.legend(ncol=3, loc="lower right", fontsize=8); ax.grid(axis="x", alpha=0.3); fig.tight_layout()
    return fig


def plot_cycles_by_period(cycles: pd.DataFrame, period: str = "month"):
    """Side-by-side cycle COUNT and mean DURATION bars, grouped by period x region."""
    fig, ax = plt.subplots(1, 2, figsize=(16, 4.5))
    cycles.groupby([period, "region"]).size().unstack(fill_value=0).plot(kind="bar", ax=ax[0])
    ax[0].set_title(f"Cycle COUNT by {period}"); ax[0].set_ylabel("cycles")
    (cycles.groupby([period, "region"]).cycle_s.mean() / 60).unstack().plot(kind="bar", ax=ax[1])
    ax[1].set_title(f"Mean cycle DURATION (min) by {period}"); ax[1].set_ylabel("min")
    for a in ax:
        a.tick_params(axis="x", rotation=90 if period == "week" else 0, labelsize=7 if period == "week" else 10)
    fig.tight_layout()
    return fig


def plot_route_breakdown(main_table: pd.DataFrame, region: str = "other"):
    """Horizontal bar of cycles per route (load->unload pair), colored by material."""
    fig, ax = plt.subplots(figsize=(11, max(3, 0.6 * len(main_table) + 1)))
    lbls = [f"{r.load}->{r.unload}\n({r.haul_km} km one-way)" for _, r in main_table.iterrows()]
    ax.barh(range(len(main_table)), main_table.cycles,
            color=[_UNLOAD_C if m == "reject" else _LOAD_C for m in main_table.load_mat])
    ax.set_yticks(range(len(main_table))); ax.set_yticklabels(lbls, fontsize=8); ax.invert_yaxis()
    for k, (_, r) in enumerate(main_table.iterrows()):
        ax.text(r.cycles, k, f" {int(r.cycles):,} ({r.share_pct}%)", va="center", fontsize=8)
    ax.set_xlabel("cycles"); ax.set_title(f"{region.upper()} — cycles by route")
    fig.tight_layout()
    return fig


def plot_truck_day(cycles: pd.DataFrame, gps_hits: pd.DataFrame, zones_gdf,
                   region: str, truck_id, day, figsize=(11, 9)):
    """All of one truck's cycle paths on one day + a printed count/mean summary.

    Used by the interactive explorer in the notebook.
    """
    sub = cycles[(cycles.tracker_id == truck_id) & (cycles.date == day)].sort_values("depart_load")
    truck = cycles.loc[cycles.tracker_id == truck_id, "truck"].iloc[0].strip()
    if len(sub) == 0:
        print(f"{truck} — {day}: 0 cycles")
        return None
    print(f"{region.upper()}  |  {truck}  |  {day}\n"
          f"  cycles = {len(sub)}   mean = {sub.cycle_s.mean()/60:.1f} min   "
          f"median = {sub.cycle_s.median()/60:.1f} min   total = {sub.cycle_s.sum()/3600:.1f} h\n"
          f"  haul = {sub.haul_s.mean()/60:.1f} min   dump = {sub.dump_s.mean()/60:.1f} min   "
          f"return = {sub.return_s.mean()/60:.1f} min   |  one-way {sub.haul_km.mean():.2f} km")
    pts = gps_hits[gps_hits.tracker_id == truck_id]
    pts = pts[pd.to_datetime(pts.get_time).dt.date == day].sort_values("get_time")
    fig, ax = plt.subplots(figsize=figsize)
    for _, z in _region_zones(zones_gdf, region).iterrows():
        xs, ys = z.geometry.exterior.xy
        c = _LOAD_C if z.zone_load_type == "load" else _UNLOAD_C
        ax.plot(xs, ys, color=c, lw=1.4, ls="-" if z.zone_load_type == "load" else "--")
        ax.fill(xs, ys, color=c, alpha=0.13, hatch=None if z.zone_load_type == "load" else "///")
        ax.annotate(str(z["label"]).strip(), (z.geometry.centroid.x, z.geometry.centroid.y),
                    fontsize=7, color=c, ha="center", bbox=dict(boxstyle="round", fc="white", ec=c, alpha=0.7))
    cmap = plt.cm.turbo(np.linspace(0, 1, len(sub)))
    for k, (_, cy) in enumerate(sub.iterrows()):
        seg = pts[(pts.get_time >= cy.depart_load) & (pts.get_time <= cy.arrive_load)]
        ax.plot(seg.lng, seg.lat, "-", color=cmap[k], lw=1.4, alpha=0.8)
    ax.set_title(f"{region.upper()} — {truck} — {day}: {len(sub)} cycles, mean {sub.cycle_s.mean()/60:.0f} min")
    ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude"); ax.axis("equal"); ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig
