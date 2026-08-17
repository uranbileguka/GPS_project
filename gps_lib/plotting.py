"""All matplotlib/seaborn visualizations for the GPS project.

Consolidates plot_tracker_paths, list_technics, and plot_zones_with_tracker_paths,
which were each defined identically in both GPS_trackpoint_analysis.ipynb and
GPS_trackpoint_route_analysis.ipynb, plus plot_zones / plot_zones_grid from
GPS_zone_analysis.ipynb.

Also adds three small helpers (plot_point_clusters, plot_routes_over_zones,
plot_route_stat_boxplots) that replace blocks of near-duplicated plotting code
that existed inline in the original route-clustering notebook (two
near-identical route-plot cells, and four near-identical boxplot cells).
"""
import math
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ZONE_COLOR_MAP = {
    "reject": "#d62728",
    "bn": "#1f77b4",
    "middling": "#2ca02c",
    "other": "#7f7f7f",
}
ZONE_MARKER_MAP = {"load": "o", "unload": "s"}

# Fixed categorical order/colors for cycle_classification.classify_segments states —
# assigned once so a state's color never shifts when the set of trackers shown changes.
STATE_ORDER = ["transit", "operating", "queuing", "unplanned_idle"]
STATE_COLOR_MAP = {
    "transit": "#2a78d6",
    "operating": "#1baf7a",
    "queuing": "#eda100",
    "unplanned_idle": "#e34948",
}


def _to_list(x):
    if x is None:
        return None
    if isinstance(x, (list, tuple, set, pd.Series, pd.Index)):
        return list(x)
    return [x]


def list_technics(df: pd.DataFrame, technic_type: str = "dump", technic_m_type: Optional[str] = None,
                   time_range=None, max_rows: int = 20) -> pd.DataFrame:
    """Return a small indexed table of unique trackers after filters, to help choose technic_idx."""
    work = df.copy()
    if technic_type is not None and "technic_type" in work.columns:
        work = work[work["technic_type"] == technic_type]
    if technic_m_type is not None and "technic_m_type" in work.columns:
        work = work[work["technic_m_type"] == technic_m_type]
        print(f"Filtered to technic_m_type='{technic_m_type}': {work['tracker_id'].nunique()} unique trackers")
    if time_range is not None:
        start, end = time_range
        work["get_time"] = pd.to_datetime(work["get_time"], errors="coerce")
        work = work[(work["get_time"] >= pd.to_datetime(start)) & (work["get_time"] <= pd.to_datetime(end))]
    counts = work.groupby(["tracker_id", "label"]).size().reset_index(name="count").sort_values("count", ascending=False)
    counts = counts.reset_index(drop=True)
    counts.insert(0, "idx", counts.index)
    return counts.head(max_rows)


def plot_tracker_paths(df: pd.DataFrame, n=None, trackers=None, technic_idx=None, technic_type="dump",
                        technic_m_type=None, time_range=None, sample="first", cmap="tab10",
                        annotate_start_end=True, figsize=(8, 8), alpha=0.85, marker="o"):
    """Plot movement paths for selected trackers ("technics") with distinct colors.

    df must contain: ['tracker_id','lat','lng','get_time','label','technic_type'].
    Selection: explicit `trackers`, or `technic_idx` (index into the filtered
    unique-tracker list), or fall back to first/random/top-N via `n`/`sample`.
    """
    required = {"tracker_id", "lat", "lng", "get_time", "label"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")

    work = df.copy()
    if "get_time" in work.columns and not np.issubdtype(work["get_time"].dtype, np.datetime64):
        work["get_time"] = pd.to_datetime(work["get_time"], errors="coerce")

    if technic_type is not None and "technic_type" in work.columns:
        work = work[work["technic_type"] == technic_type]
    if technic_m_type is not None and "technic_m_type" in work.columns:
        work = work[work["technic_m_type"] == technic_m_type]
        print(f"Filtered to technic_m_type='{technic_m_type}': {work['tracker_id'].nunique()} unique trackers")
    if time_range is not None:
        start, end = pd.to_datetime(time_range[0]), pd.to_datetime(time_range[1])
        work = work[(work["get_time"] >= start) & (work["get_time"] <= end)]

    unique_ids = pd.Series(work["tracker_id"].dropna()).drop_duplicates().reset_index(drop=True)

    if trackers is not None:
        trackers = list(trackers) if isinstance(trackers, (list, tuple, set, pd.Series, pd.Index)) else [trackers]
    elif technic_idx is not None:
        idx_list = [int(i) for i in (technic_idx if isinstance(technic_idx, (list, tuple, set, pd.Series, pd.Index)) else [technic_idx])]
        max_idx = len(unique_ids) - 1
        for i in idx_list:
            if i < 0 or i > max_idx:
                raise IndexError(f"technic_idx {i} is out of range [0..{max_idx}] after filtering")
        trackers = [unique_ids.iloc[i] for i in idx_list]
    else:
        n = 1 if (n is None) else int(n)
        if unique_ids.empty:
            print("No tracker ids available after filtering.")
            return None, None
        if sample == "random":
            trackers = list(unique_ids.sample(min(n, len(unique_ids))).tolist())
        elif sample == "top":
            counts = work.groupby("tracker_id").size().sort_values(ascending=False)
            trackers = counts.index.tolist()[:n]
        else:
            trackers = unique_ids.head(n).tolist()

    if not trackers:
        print("Tracker list empty.")
        return None, None

    cmap_obj = plt.colormaps[cmap].resampled(len(trackers))
    fig, ax = plt.subplots(figsize=figsize)

    for i, tid in enumerate(trackers):
        g = work[work["tracker_id"] == tid].dropna(subset=["lat", "lng"]).sort_values("get_time")
        if g.empty:
            continue
        color = cmap_obj(i)
        label = g["label"].iloc[0] if "label" in g.columns else f"Tracker {tid}"
        ax.plot(g["lng"], g["lat"], marker + "-", color=color, linewidth=2, alpha=alpha,
                label=f"{label} ({tid})")
        if annotate_start_end:
            sx, sy = g["lng"].iloc[0], g["lat"].iloc[0]
            ex, ey = g["lng"].iloc[-1], g["lat"].iloc[-1]
            ax.scatter([sx], [sy], c=[color], marker="^", s=60, edgecolor="k", linewidth=0.5)
            ax.scatter([ex], [ey], c=[color], marker="s", s=60, edgecolor="k", linewidth=0.5)
            ax.text(sx, sy, "S", fontsize=9, ha="center", va="bottom", color="k")
            ax.text(ex, ey, "E", fontsize=9, ha="center", va="top", color="k")

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Tracker Paths" + (f" ({technic_type})" if technic_type else ""))
    ax.grid(True)
    ax.axis("equal")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    plt.show()
    return fig, ax


def plot_zones(df: pd.DataFrame, meta_df: pd.DataFrame, material_types=None, load_types=None,
                zone_ids=None, figsize=(9, 8), show_legend=True, unload_hatch="///",
                unload_edge_style="--", unload_alpha=0.15, load_alpha=0.30):
    """Plot zone polygons: color = material type, marker/fill = load type (unload hatched).

    df: ['zone_id','lat','lng'] polygon points (in draw order).
    meta_df: ['id','label','zone_material_type','zone_load_type'].
    """
    req_poly = {"zone_id", "lat", "lng"}
    if not req_poly.issubset(df.columns):
        raise ValueError(f"df missing required columns: {req_poly - set(df.columns)}")
    req_meta = {"id", "label", "zone_material_type", "zone_load_type"}
    if not req_meta.issubset(meta_df.columns):
        raise ValueError(f"meta_df missing required columns: {req_meta - set(meta_df.columns)}")

    zm = pd.merge(df, meta_df[list(req_meta)].drop_duplicates("id"),
                   left_on="zone_id", right_on="id", how="left").dropna(subset=["lat", "lng"])

    material_types, load_types, zone_ids = _to_list(material_types), _to_list(load_types), _to_list(zone_ids)
    if material_types is not None:
        zm = zm[zm["zone_material_type"].isin(material_types)]
    if load_types is not None:
        zm = zm[zm["zone_load_type"].isin(load_types)]
    if zone_ids is not None:
        zm = zm[zm["zone_id"].isin(zone_ids)]

    if zm.empty:
        print("No zones match given filters.")
        return None

    fig, ax = plt.subplots(figsize=figsize)

    for zid, grp in zm.groupby("zone_id", sort=False):
        grp = grp.dropna(subset=["lng", "lat"])
        if grp.empty:
            continue
        xs, ys = grp["lng"].tolist(), grp["lat"].tolist()
        if len(xs) >= 2 and (xs[0] != xs[-1] or ys[0] != ys[-1]):
            xs.append(xs[0]); ys.append(ys[0])

        material = grp["zone_material_type"].iloc[0] if "zone_material_type" in grp.columns else "other"
        load = grp["zone_load_type"].iloc[0] if "zone_load_type" in grp.columns else "unload"
        label = grp["label"].iloc[0] if "label" in grp.columns else f"Zone {zid}"
        color = ZONE_COLOR_MAP.get(material, ZONE_COLOR_MAP["other"])
        marker = ZONE_MARKER_MAP.get(load, "o")

        line_style = unload_edge_style if load == "unload" else "-"
        ax.plot(xs, ys, color=color, linestyle=line_style, linewidth=2, alpha=0.95)
        if load == "unload":
            ax.fill(xs, ys, facecolor=color, alpha=unload_alpha, hatch=unload_hatch, edgecolor=color, linewidth=1)
        else:
            ax.fill(xs, ys, facecolor=color, alpha=load_alpha, edgecolor=color, linewidth=1)

        ax.scatter(grp["lng"], grp["lat"], s=14, c=color, marker=marker, edgecolor="k", linewidths=0.35, alpha=0.9)
        ax.text(xs[0], ys[0], label, fontsize=8, ha="left", va="bottom", color=color)

    if show_legend:
        materials_present = sorted(zm["zone_material_type"].dropna().unique())
        material_handles = [
            Patch(facecolor=ZONE_COLOR_MAP.get(m, ZONE_COLOR_MAP["other"]), edgecolor="none", alpha=0.6, label=m)
            for m in materials_present
        ]
        loads_present = sorted(zm["zone_load_type"].dropna().unique())
        load_handles = [
            Line2D([0], [0], marker=ZONE_MARKER_MAP.get(ld, "o"), color="k",
                   markerfacecolor=ZONE_COLOR_MAP.get(materials_present[0] if materials_present else "other", "k"),
                   markeredgecolor="k", markersize=8, linestyle="None", label=ld)
            for ld in loads_present
        ]
        legend1 = ax.legend(handles=material_handles, title="zone_material_type (color)", loc="upper left")
        ax.add_artist(legend1)
        ax.legend(handles=load_handles, title="zone_load_type (shape)", loc="lower left")

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Zones: color = material type, shape = load type (unload hatched)")
    ax.grid(True)
    ax.axis("equal")
    fig.tight_layout()
    plt.show()
    return ax


def plot_zones_grid(df: pd.DataFrame, meta_df: pd.DataFrame, zone_ids=None, ncols=4,
                     figsize_per_plot=(4, 4), share_axes=False, hatch_unload="///",
                     unload_alpha=0.15, load_alpha=0.30):
    """Show zone polygons in a grid; unload zones get a hatched fill, load zones solid."""
    required_df_cols = {"zone_id", "lat", "lng"}
    if not required_df_cols.issubset(df.columns):
        raise ValueError(f"df is missing required columns: {required_df_cols - set(df.columns)}")
    required_meta_cols = {"id", "label", "zone_material_type", "zone_load_type"}
    if not required_meta_cols.issubset(meta_df.columns):
        raise ValueError(f"meta_df is missing required columns: {required_meta_cols - set(meta_df.columns)}")

    if zone_ids is None:
        zone_ids = df["zone_id"].dropna().unique().tolist()
    nplots = len(zone_ids)
    if nplots == 0:
        print("No zones to plot.")
        return None, None

    meta_df = meta_df[list(required_meta_cols)].drop_duplicates("id")
    label_map = meta_df.set_index("id")["label"].to_dict()
    mat_map = meta_df.set_index("id")["zone_material_type"].to_dict()
    load_map = meta_df.set_index("id")["zone_load_type"].to_dict()

    ncols = max(1, int(ncols))
    nrows = math.ceil(nplots / ncols)
    fig_w, fig_h = max(4, ncols * figsize_per_plot[0]), max(3, nrows * figsize_per_plot[1])
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h), squeeze=False,
                              sharex=share_axes, sharey=share_axes)

    for idx in range(nrows * ncols):
        r, c = divmod(idx, ncols)
        ax = axes[r, c]
        if idx >= nplots:
            ax.axis("off")
            continue

        zid = zone_ids[idx]
        poly = df[df["zone_id"] == zid].dropna(subset=["lat", "lng"])
        if poly.empty:
            ax.text(0.5, 0.5, f"No data for zone {zid}", ha="center", va="center", transform=ax.transAxes)
            ax.axis("off")
            continue

        xs, ys = poly["lng"].tolist(), poly["lat"].tolist()
        if len(xs) >= 2 and (xs[0] != xs[-1] or ys[0] != ys[-1]):
            xs.append(xs[0]); ys.append(ys[0])

        material = mat_map.get(zid, "other")
        load_type = load_map.get(zid, "unload")
        color = ZONE_COLOR_MAP.get(material, ZONE_COLOR_MAP["other"])

        ax.plot(xs, ys, color=color, linewidth=2)
        if load_type == "unload":
            ax.fill(xs, ys, facecolor=color, alpha=unload_alpha, hatch=hatch_unload, edgecolor=color, linewidth=1)
        else:
            ax.fill(xs, ys, facecolor=color, alpha=load_alpha, edgecolor=color, linewidth=1)

        ax.set_title(f"{label_map.get(zid, f'Zone {zid}')}\n{material} | {load_type}", fontsize=9)
        ax.set_xlabel("Lng")
        ax.set_ylabel("Lat")
        ax.grid(True)
        ax.axis("equal")

    fig.tight_layout()
    plt.show()
    return fig, axes


def plot_zones_with_tracker_paths(zone_df: pd.DataFrame, zone_meta_df: pd.DataFrame, tracker_df: pd.DataFrame,
                                   material_types=None, load_types=None, zone_ids=None,
                                   n=None, trackers=None, technic_idx=None, technic_type="dump",
                                   technic_m_type=None, figsize=(12, 10), show_legend=True,
                                   unload_hatch="///", unload_alpha=0.15, load_alpha=0.30):
    """Plot zone polygons and tracker paths together on one figure."""
    req_zone = {"zone_id", "lat", "lng"}
    if not req_zone.issubset(zone_df.columns):
        raise ValueError(f"zone_df missing: {req_zone - set(zone_df.columns)}")
    req_meta = {"id", "label", "zone_material_type", "zone_load_type"}
    if not req_meta.issubset(zone_meta_df.columns):
        raise ValueError(f"zone_meta_df missing: {req_meta - set(zone_meta_df.columns)}")
    req_tracker = {"tracker_id", "lat", "lng", "get_time", "label"}
    if not req_tracker.issubset(tracker_df.columns):
        raise ValueError(f"tracker_df missing: {req_tracker - set(tracker_df.columns)}")

    zm = pd.merge(zone_df, zone_meta_df[list(req_meta)].drop_duplicates("id"),
                   left_on="zone_id", right_on="id", how="left").dropna(subset=["lat", "lng"])

    material_types, load_types, zone_ids = _to_list(material_types), _to_list(load_types), _to_list(zone_ids)
    if material_types is not None:
        zm = zm[zm["zone_material_type"].isin(material_types)]
    if load_types is not None:
        zm = zm[zm["zone_load_type"].isin(load_types)]
    if zone_ids is not None:
        zm = zm[zm["zone_id"].isin(zone_ids)]

    work = tracker_df.copy()
    if "get_time" in work.columns and not np.issubdtype(work["get_time"].dtype, np.datetime64):
        work["get_time"] = pd.to_datetime(work["get_time"], errors="coerce")
    if technic_type is not None and "technic_type" in work.columns:
        work = work[work["technic_type"] == technic_type]
    if technic_m_type is not None and "technic_m_type" in work.columns:
        work = work[work["technic_m_type"] == technic_m_type]
        print(f"Filtered to technic_m_type='{technic_m_type}': {work['tracker_id'].nunique()} unique trackers")

    unique_ids = pd.Series(work["tracker_id"].dropna()).drop_duplicates().reset_index(drop=True)
    if trackers is not None:
        trackers = list(trackers) if isinstance(trackers, (list, tuple, set, pd.Series, pd.Index)) else [trackers]
    elif technic_idx is not None:
        idx_list = [int(i) for i in (technic_idx if isinstance(technic_idx, (list, tuple, set, pd.Series, pd.Index)) else [technic_idx])]
        max_idx = len(unique_ids) - 1
        for i in idx_list:
            if i < 0 or i > max_idx:
                raise IndexError(f"technic_idx {i} out of range [0..{max_idx}]")
        trackers = [unique_ids.iloc[i] for i in idx_list]
    else:
        n = 1 if (n is None) else int(n)
        trackers = [] if unique_ids.empty else unique_ids.head(n).tolist()

    fig, ax = plt.subplots(figsize=figsize)

    for zid, grp in zm.groupby("zone_id", sort=False):
        grp = grp.dropna(subset=["lng", "lat"])
        if grp.empty:
            continue
        xs, ys = grp["lng"].tolist(), grp["lat"].tolist()
        if len(xs) >= 2 and (xs[0] != xs[-1] or ys[0] != ys[-1]):
            xs.append(xs[0]); ys.append(ys[0])

        material = grp["zone_material_type"].iloc[0] if "zone_material_type" in grp.columns else "other"
        load = grp["zone_load_type"].iloc[0] if "zone_load_type" in grp.columns else "unload"
        color = ZONE_COLOR_MAP.get(material, ZONE_COLOR_MAP["other"])

        line_style = "--" if load == "unload" else "-"
        ax.plot(xs, ys, color=color, linestyle=line_style, linewidth=2, alpha=0.7)
        if load == "unload":
            ax.fill(xs, ys, facecolor=color, alpha=unload_alpha, hatch=unload_hatch, edgecolor=color, linewidth=1)
        else:
            ax.fill(xs, ys, facecolor=color, alpha=load_alpha, edgecolor=color, linewidth=1)

    tracker_cmap = plt.colormaps["plasma"].resampled(max(len(trackers), 1))
    for i, tid in enumerate(trackers):
        g = work[work["tracker_id"] == tid].dropna(subset=["lat", "lng"]).sort_values("get_time")
        if g.empty:
            continue
        color = tracker_cmap(i)
        tlabel = g["label"].iloc[0] if "label" in g.columns else f"Tracker {tid}"
        ax.plot(g["lng"], g["lat"], "o-", color=color, linewidth=3, alpha=0.9, markersize=6,
                label=f"{tlabel} ({tid})")
        sx, sy = g["lng"].iloc[0], g["lat"].iloc[0]
        ex, ey = g["lng"].iloc[-1], g["lat"].iloc[-1]
        ax.scatter([sx], [sy], c=[color], marker="^", s=100, edgecolor="k", linewidth=1.5, zorder=10)
        ax.scatter([ex], [ey], c=[color], marker="s", s=100, edgecolor="k", linewidth=1.5, zorder=10)
        ax.text(sx, sy, "S", fontsize=10, ha="center", va="bottom", color="white", weight="bold", zorder=11)
        ax.text(ex, ey, "E", fontsize=10, ha="center", va="top", color="white", weight="bold", zorder=11)

    if show_legend:
        materials_present = sorted(zm["zone_material_type"].dropna().unique()) if not zm.empty else []
        material_handles = [
            Patch(facecolor=ZONE_COLOR_MAP.get(m, ZONE_COLOR_MAP["other"]), edgecolor="none", alpha=0.6, label=f"Zone: {m}")
            for m in materials_present
        ]
        tracker_handles, _ = ax.get_legend_handles_labels()
        ax.legend(handles=material_handles + tracker_handles, title="Zones & Trackers", loc="best", fontsize=9)

    ax.set_xlabel("Longitude", fontsize=11)
    ax.set_ylabel("Latitude", fontsize=11)
    ax.set_title("Zone Polygons + Tracker Paths", fontsize=13)
    ax.grid(True, alpha=0.3)
    ax.axis("equal")
    fig.tight_layout()
    plt.show()
    return fig, ax


def plot_point_clusters(zones_target_gdf, points_df: pd.DataFrame, cluster_col: str = "cluster",
                         figsize=(10, 10)):
    """Plot zone polygons with raw GPS points colored by cluster id (KMeans on points)."""
    k = points_df[cluster_col].nunique()
    fig, ax = plt.subplots(figsize=figsize)

    for _, row in zones_target_gdf.iterrows():
        color = "red" if row["zone_material_type"] == "reject" else "green"
        zones_target_gdf[zones_target_gdf["zone_id"] == row["zone_id"]].plot(
            ax=ax, edgecolor=color, facecolor=color, alpha=0.25
        )

    colors = plt.cm.tab10(np.linspace(0, 1, k))
    for cluster_id in range(k):
        g = points_df[points_df[cluster_col] == cluster_id]
        for _, seg in g.groupby("tracker_id"):
            ax.plot(seg["lng"], seg["lat"], color=colors[cluster_id], linewidth=1, alpha=0.7)

    ax.set_title("Clusters of Dump Truck Tracks")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    plt.show()
    return fig, ax


def plot_routes_over_zones(zones_target_gdf, routes: list, color_by: Optional[str] = None,
                            k: Optional[int] = None, figsize=(6, 8)):
    """Plot extracted routes over their zone polygons.

    color_by=None  -> each route gets its own color (route_idx), legend shown if <=10 routes.
    color_by='cluster' -> routes colored by their assigned cluster (requires k and a
        'cluster' key on each route dict, set by clustering.kmeans_cluster_route_shapes).
    """
    fig, ax = plt.subplots(figsize=figsize)

    for _, row in zones_target_gdf.iterrows():
        geom = row["geometry"]
        if geom is None:
            continue
        x, y = geom.exterior.xy
        if row["zone_material_type"] == "reject":
            ax.fill(x, y, facecolor="mistyrose", edgecolor="red", alpha=0.35, linestyle="--")
        else:
            ax.fill(x, y, facecolor="honeydew", edgecolor="green", alpha=0.35, linestyle="--")

    n_routes = len(routes)
    if color_by == "cluster":
        if k is None:
            raise ValueError("k is required when color_by='cluster'")
        palette = plt.cm.tab10(np.linspace(0, 1, k))
        colors = [palette[r["cluster"]] for r in routes]
        title = f"Clustered Routes (k={k}, n={n_routes})"
    else:
        palette = plt.cm.tab20(np.linspace(0, 1, max(n_routes, 1)))
        colors = list(palette)
        title = f"Routes ({n_routes} segments)"

    for ridx, r in enumerate(routes):
        seg = pd.DataFrame(r["points"])
        if seg.empty:
            continue
        c = colors[ridx]
        label = f"route {ridx}" if (color_by is None and n_routes <= 10) else None
        ax.plot(seg["lng"], seg["lat"], color=c, linewidth=1.2, alpha=0.9, label=label)
        ax.scatter(seg["lng"].iloc[0], seg["lat"].iloc[0], color=c, marker="o", s=25, zorder=5)
        ax.scatter(seg["lng"].iloc[-1], seg["lat"].iloc[-1], color=c, marker="x", s=40, zorder=5)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    if color_by is None and n_routes <= 10:
        ax.legend(loc="best")
    plt.show()
    return fig, ax


def plot_route_stat_boxplots(route_stats: pd.DataFrame, metrics=("distance_m", "duration_sec", "tortuosity", "noise_index"),
                              cluster_col="cluster", figsize=(10, 6)):
    """Boxplot + stripplot of route_stats metrics grouped by cluster, one figure per metric."""
    titles = {
        "distance_m": ("Route Distance by Cluster", "Distance (meters)"),
        "duration_sec": ("Route Duration by Cluster", "Duration (seconds)"),
        "tortuosity": ("Route Tortuosity by Cluster", "Tortuosity"),
        "noise_index": ("Route Noise Index by Cluster", "Noise Index (higher = more turns)"),
    }
    for metric in metrics:
        plt.figure(figsize=figsize)
        sns.boxplot(data=route_stats, x=cluster_col, y=metric, palette="tab20")
        sns.stripplot(data=route_stats, x=cluster_col, y=metric, color="black", alpha=0.4)
        title, ylabel = titles.get(metric, (metric, metric))
        plt.title(title)
        plt.ylabel(ylabel)
        plt.xlabel("Cluster")
        plt.show()


def plot_state_breakdown_by_tracker(breakdown_df: pd.DataFrame, n_trackers=3,
                                     label_map: Optional[dict] = None,
                                     bar_height: float = 0.45, min_figsize=(8, 3)):
    """Stacked horizontal bar chart of per-tracker state-time share.

    breakdown_df: output of cycle_classification.state_time_breakdown_by_tracker
        (index = tracker_id, columns = state, values = fraction of that
        tracker's own tracked time — rows sum to 1.0).
    n_trackers: how many trackers to plot — an int (first N rows of
        breakdown_df), or "all" to plot every tracker in it.
    label_map: optional {tracker_id: display_label}, e.g.
        tracker_list_df.set_index("id")["label"].to_dict(), used for the
        y-axis tick labels instead of raw tracker_id.
    """
    work = breakdown_df if n_trackers == "all" else breakdown_df.head(int(n_trackers))
    if work.empty:
        print("No trackers to plot.")
        return None, None

    states = [s for s in STATE_ORDER if s in work.columns] + \
             [s for s in work.columns if s not in STATE_ORDER]

    fig_h = max(min_figsize[1], bar_height * len(work) + 1.2)
    fig, ax = plt.subplots(figsize=(min_figsize[0], fig_h))

    y_pos = np.arange(len(work))
    left = np.zeros(len(work))
    for state in states:
        vals = (work[state] * 100).to_numpy()
        color = STATE_COLOR_MAP.get(state, "#898781")
        ax.barh(y_pos, vals, left=left, height=0.7, color=color,
                edgecolor="white", linewidth=0.5, label=state)
        for yi, (v, l0) in enumerate(zip(vals, left)):
            if v >= 4:  # selective labeling — skip slivers too small to hold text
                ax.text(l0 + v / 2, yi, f"{v:.0f}%", ha="center", va="center",
                         fontsize=8, color="black")
        left += vals

    labels = [label_map.get(tid, str(tid)) if label_map else str(tid) for tid in work.index]
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of tracked time (%)")
    ax.set_title(f"State-time breakdown by truck (dt-weighted), n={len(work)}")
    ax.grid(axis="x", alpha=0.3)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=len(states),
              fontsize=9, frameon=False)
    fig.tight_layout()
    plt.show()
    return fig, ax


def plot_state_map(classified_df: pd.DataFrame, zones_gdf, n_trackers=3, tracker_ids=None,
                    label_map: Optional[dict] = None, figsize=(10, 10),
                    point_size: float = 6, zone_alpha: float = 0.12):
    """Plot GPS pings on the map, colored by classify_segments state — the
    spatial counterpart to plot_state_breakdown_by_tracker.

    classified_df: output of cycle_classification.classify_segments (needs
        tracker_id, lat, lng, state columns).
    zones_gdf: zone polygons (zones.build_zone_geodataframe output), drawn
        underneath as light context, colored by zone_material_type.
    n_trackers / tracker_ids: pick trucks the same way as
        plot_state_breakdown_by_tracker — explicit tracker_ids, or the
        first n_trackers (int or "all") by order of first appearance.
    """
    if tracker_ids is not None:
        trackers = list(tracker_ids) if isinstance(tracker_ids, (list, tuple, set, pd.Series, pd.Index)) else [tracker_ids]
    else:
        unique_ids = pd.Series(classified_df["tracker_id"].dropna()).drop_duplicates().reset_index(drop=True)
        trackers = unique_ids.tolist() if n_trackers == "all" else unique_ids.head(int(n_trackers)).tolist()

    work = classified_df[classified_df["tracker_id"].isin(trackers)]
    if work.empty:
        print("No pings to plot for the selected trackers.")
        return None, None

    fig, ax = plt.subplots(figsize=figsize)

    if zones_gdf is not None:
        for _, row in zones_gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            color = ZONE_COLOR_MAP.get(row.get("zone_material_type"), ZONE_COLOR_MAP["other"])
            x, y = geom.exterior.xy
            ax.fill(x, y, facecolor=color, edgecolor=color, alpha=zone_alpha, linewidth=1)

    present_states = work["state"].dropna().unique()
    states = [s for s in STATE_ORDER if s in present_states] + \
             [s for s in present_states if s not in STATE_ORDER]
    for state in states:
        g = work[work["state"] == state]
        ax.scatter(g["lng"], g["lat"], s=point_size, c=STATE_COLOR_MAP.get(state, "#898781"),
                   label=state, alpha=0.7, edgecolors="none")

    if len(trackers) <= 6:
        names = [str(label_map.get(t, t)) if label_map else str(t) for t in trackers]
        title = f"Ping states on map — {', '.join(names)}"
    else:
        title = f"Ping states on map — {len(trackers)} trucks"

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=9, markerscale=2)
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.show()
    return fig, ax


def plot_state_map_grid(classified_df: pd.DataFrame, zones_gdf, n_trackers=3, tracker_ids=None,
                         label_map: Optional[dict] = None, ncols: int = 3,
                         figsize_per_plot=(4, 4), point_size: float = 5,
                         zone_alpha: float = 0.12, share_axes: bool = False):
    """Small-multiples version of plot_state_map: one map subplot per truck,
    pings colored by state, so trucks can be compared side by side instead
    of overlaid on a single crowded map.

    classified_df / zones_gdf / n_trackers / tracker_ids / label_map: same
        meaning as plot_state_map.
    """
    if tracker_ids is not None:
        trackers = list(tracker_ids) if isinstance(tracker_ids, (list, tuple, set, pd.Series, pd.Index)) else [tracker_ids]
    else:
        unique_ids = pd.Series(classified_df["tracker_id"].dropna()).drop_duplicates().reset_index(drop=True)
        trackers = unique_ids.tolist() if n_trackers == "all" else unique_ids.head(int(n_trackers)).tolist()

    if not trackers:
        print("No trackers to plot.")
        return None, None

    present_states = classified_df["state"].dropna().unique()
    states = [s for s in STATE_ORDER if s in present_states] + \
             [s for s in present_states if s not in STATE_ORDER]

    ncols = max(1, int(ncols))
    nrows = math.ceil(len(trackers) / ncols)
    fig_w, fig_h = max(4, ncols * figsize_per_plot[0]), max(3, nrows * figsize_per_plot[1])
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h), squeeze=False,
                              sharex=share_axes, sharey=share_axes)

    for idx in range(nrows * ncols):
        r, c = divmod(idx, ncols)
        ax = axes[r, c]
        if idx >= len(trackers):
            ax.axis("off")
            continue

        tid = trackers[idx]
        g = classified_df[classified_df["tracker_id"] == tid]

        if zones_gdf is not None:
            for _, row in zones_gdf.iterrows():
                geom = row.geometry
                if geom is None:
                    continue
                color = ZONE_COLOR_MAP.get(row.get("zone_material_type"), ZONE_COLOR_MAP["other"])
                x, y = geom.exterior.xy
                ax.fill(x, y, facecolor=color, edgecolor=color, alpha=zone_alpha, linewidth=1)

        for state in states:
            gs = g[g["state"] == state]
            if gs.empty:
                continue
            ax.scatter(gs["lng"], gs["lat"], s=point_size, c=STATE_COLOR_MAP.get(state, "#898781"),
                       alpha=0.75, edgecolors="none")

        title = str(label_map.get(tid, tid)) if label_map else str(tid)
        ax.set_title(f"{title} ({tid})" if label_map else title, fontsize=9)
        ax.set_xlabel("Lng", fontsize=8)
        ax.set_ylabel("Lat", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.axis("equal")
        ax.grid(True, alpha=0.3)

    handles = [Patch(facecolor=STATE_COLOR_MAP.get(s, "#898781"), edgecolor="none", label=s) for s in states]
    fig.legend(handles=handles, loc="lower center", ncol=len(states), fontsize=9, frameon=False,
               bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(f"Ping states by truck (n={len(trackers)})", fontsize=12)
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])
    plt.show()
    return fig, axes


# Reserved status color (never a categorical series identity) — marks a
# flagged/actionable finding, here: a DBSCAN cluster with no zone match.
CANDIDATE_ZONE_COLOR = "#d03b3b"


def plot_candidate_zones(candidate_df: pd.DataFrame, zones_gdf, top_n: int = 10,
                          figsize=(9, 9), zone_alpha: float = 0.15):
    """Plot candidate missing-zone locations over the surveyed zone polygons.

    candidate_df: output of stops.candidate_missing_zones (index = stop_cluster;
        columns lat, lng, total_dwell_hr, n_pings, n_trackers). Marker size is
        scaled by total_dwell_hr; markers are numbered by rank (1 = most dwell
        time) so they can be cross-referenced against the printed table.
    """
    work = candidate_df.head(top_n)
    if work.empty:
        print("No candidate clusters to plot.")
        return None, None

    fig, ax = plt.subplots(figsize=figsize)

    if zones_gdf is not None:
        for _, row in zones_gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            color = ZONE_COLOR_MAP.get(row.get("zone_material_type"), ZONE_COLOR_MAP["other"])
            x, y = geom.exterior.xy
            ax.fill(x, y, facecolor=color, edgecolor=color, alpha=zone_alpha, linewidth=1)

    max_dwell = work["total_dwell_hr"].max()
    sizes = 80 + 400 * (work["total_dwell_hr"] / max_dwell) if max_dwell > 0 else 120
    ax.scatter(work["lng"], work["lat"], s=sizes, c=CANDIDATE_ZONE_COLOR, edgecolors="white",
               linewidths=1.2, alpha=0.85, zorder=5)
    for rank, (_, row) in enumerate(work.iterrows(), start=1):
        ax.annotate(str(rank), (row["lng"], row["lat"]), ha="center", va="center",
                    fontsize=8, color="white", weight="bold", zorder=6)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"Top {len(work)} candidate missing-zone locations\n"
                 "(dense DBSCAN stop clusters outside all surveyed zones; marker size = total dwell hours)")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.show()
    return fig, ax


def plot_dbscan_stop_clusters(labeled_stops: pd.DataFrame, zones_gdf, figsize=(10, 10),
                               point_size: float = 8, zone_alpha: float = 0.15,
                               noise_color: str = "#c3c2b7", annotate_clusters: bool = True):
    """Plot every DBSCAN stop cluster (stops.cluster_and_label_stops output)
    over the zone polygons, colored by cluster id, with noise pings shown
    separately in muted gray.

    Cluster ids are algorithm-assigned, not a fixed identity set (the count
    varies with eps/min_samples), so colors cycle through a qualitative
    colormap rather than a fixed categorical palette — same convention as
    plot_point_clusters/plot_routes_over_zones elsewhere in this module.
    Each cluster's centroid is ringed in black if it matched a known zone,
    or in the reserved "candidate" red if it didn't (zone_mat_hit == "unplanned").
    """
    fig, ax = plt.subplots(figsize=figsize)

    if zones_gdf is not None:
        for _, row in zones_gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            color = ZONE_COLOR_MAP.get(row.get("zone_material_type"), ZONE_COLOR_MAP["other"])
            x, y = geom.exterior.xy
            ax.fill(x, y, facecolor=color, edgecolor=color, alpha=zone_alpha, linewidth=1)

    noise = labeled_stops[labeled_stops["stop_cluster"] == -1]
    ax.scatter(noise["lng"], noise["lat"], s=point_size, c=noise_color, alpha=0.5,
               edgecolors="none", label=f"noise (n={len(noise)})", zorder=3)

    cluster_ids = sorted(labeled_stops.loc[labeled_stops["stop_cluster"] != -1, "stop_cluster"].unique())
    cmap = plt.colormaps["tab20"].resampled(max(len(cluster_ids), 1))
    for i, cid in enumerate(cluster_ids):
        g = labeled_stops[labeled_stops["stop_cluster"] == cid]
        color = cmap(i)
        ax.scatter(g["lng"], g["lat"], s=point_size, c=[color], alpha=0.8, edgecolors="none", zorder=4)
        if annotate_clusters:
            clat, clng = g["lat"].mean(), g["lng"].mean()
            matched = g["zone_mat_hit"].iloc[0] != "unplanned"
            ax.scatter([clng], [clat], s=100, facecolors="none",
                       edgecolors="black" if matched else CANDIDATE_ZONE_COLOR,
                       linewidths=1.4, zorder=6)
            ax.annotate(str(cid), (clng, clat), fontsize=7, ha="center", va="center", zorder=7)

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(f"DBSCAN stop clusters over zone map "
                 f"(n_clusters={len(cluster_ids)}, noise={len(noise)}/{len(labeled_stops)})")
    ax.legend(loc="best", fontsize=9, markerscale=2)
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.show()
    return fig, ax
