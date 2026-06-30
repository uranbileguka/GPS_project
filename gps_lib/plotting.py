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
        trackers = list(trackers) if isinstance(trackers, (list, tuple, set, pd.Series)) else [trackers]
    elif technic_idx is not None:
        idx_list = [int(i) for i in (technic_idx if isinstance(technic_idx, (list, tuple, set, pd.Series)) else [technic_idx])]
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
        trackers = list(trackers) if isinstance(trackers, (list, tuple, set, pd.Series)) else [trackers]
    elif technic_idx is not None:
        idx_list = [int(i) for i in (technic_idx if isinstance(technic_idx, (list, tuple, set, pd.Series)) else [technic_idx])]
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
