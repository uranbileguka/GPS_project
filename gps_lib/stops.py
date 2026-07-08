"""DBSCAN-based stop/queue detection over low-speed GPS pings (Section 4.2)."""
import pandas as pd

from . import clustering
from . import zones as zones_mod


def filter_stop_pings(df: pd.DataFrame, speed_col: str = "speed", speed_threshold: float = 2.0) -> pd.DataFrame:
    """Pings where the truck is effectively stationary."""
    if speed_col not in df.columns:
        return df.copy()
    return df[df[speed_col] < speed_threshold].copy()


def cluster_and_label_stops(stop_df: pd.DataFrame, zones_gdf, eps_m: float = 30.0,
                             min_samples: int = 3) -> pd.DataFrame:
    """Run DBSCAN over stop pings, then label each cluster by whether its
    centroid falls inside a known zone polygon.

    Adds `stop_cluster` (-1 = noise, not part of any dense stop cluster),
    `zone_id_hit`, `zone_mat_hit`, `zone_load_hit` to stop_df. Clustered
    pings (stop_cluster != -1) whose cluster matched no zone polygon are
    labeled "unplanned" — stop locations outside any surveyed zone.
    """
    df = stop_df.copy()
    coords = df[["lat", "lng"]].values
    df["stop_cluster"] = clustering.dbscan_cluster_stops(coords, eps_m=eps_m, min_samples=min_samples)

    centroids = (
        df[df["stop_cluster"] != -1]
        .groupby("stop_cluster")[["lat", "lng"]]
        .mean()
        .reset_index()
    )
    if centroids.empty:
        df["zone_id_hit"] = None
        df["zone_mat_hit"] = "noise"
        df["zone_load_hit"] = "noise"
        return df

    hits = zones_mod.assign_zone_hit(centroids, zones_gdf)
    hits["zone_mat_hit"] = hits["zone_mat_hit"].fillna("unplanned")
    hits["zone_load_hit"] = hits["zone_load_hit"].fillna("unplanned")
    cluster_labels = hits[["stop_cluster", "zone_id_hit", "zone_mat_hit", "zone_load_hit"]]

    df = df.merge(cluster_labels, on="stop_cluster", how="left")
    noise = df["stop_cluster"] == -1
    df.loc[noise, "zone_mat_hit"] = "noise"
    df.loc[noise, "zone_load_hit"] = "noise"
    return df


def unplanned_idle_share(labeled_stop_df: pd.DataFrame) -> float:
    """Fraction of clustered (non-noise) stop pings whose cluster matched no zone."""
    clustered = labeled_stop_df[labeled_stop_df["stop_cluster"] != -1]
    if clustered.empty:
        return float("nan")
    return float((clustered["zone_mat_hit"] == "unplanned").mean())


def dbscan_sensitivity_sweep(stop_df: pd.DataFrame, zones_gdf, eps_values, min_samples_values) -> pd.DataFrame:
    """Re-run cluster_and_label_stops across an eps x min_samples grid.

    Reports how the number of clusters and the unplanned-idle share shift
    with the DBSCAN parameters — the sensitivity check called for in
    Section 4.6 / TASKS.md Section C.
    """
    rows = []
    for eps_m in eps_values:
        for min_samples in min_samples_values:
            labeled = cluster_and_label_stops(stop_df, zones_gdf, eps_m=eps_m, min_samples=min_samples)
            n_clusters = labeled.loc[labeled["stop_cluster"] != -1, "stop_cluster"].nunique()
            n_noise = int((labeled["stop_cluster"] == -1).sum())
            rows.append({
                "eps_m": eps_m,
                "min_samples": min_samples,
                "n_clusters": n_clusters,
                "n_noise_pings": n_noise,
                "noise_share": n_noise / len(labeled) if len(labeled) else float("nan"),
                "unplanned_idle_share": unplanned_idle_share(labeled),
            })
    return pd.DataFrame(rows)
