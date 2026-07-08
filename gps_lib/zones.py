"""Zone polygon construction and point-in-zone lookups.

Two separate polygon representations are kept, matching the two different
original use cases:
- build_ordered_zone_polygons: an ordered, ring-closed point list for
  matplotlib plotting (plotting.plot_zones / plot_zones_grid).
- build_zone_geodataframe: a shapely/geopandas GeoDataFrame for fast
  point-in-polygon "zone hit" testing (assign_zone_hit).
"""
import numpy as np
import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Polygon
except ImportError:  # geopandas/shapely only needed for shapely-based zone hit testing
    gpd = None


def order_and_close_ring(zone_points: pd.DataFrame) -> pd.DataFrame:
    """Order one zone's vertices around their centroid and close the ring."""
    g = zone_points[["zone_id", "lat", "lng"]].dropna().drop_duplicates()
    cx, cy = g["lng"].mean(), g["lat"].mean()
    angles = np.arctan2(g["lat"] - cy, g["lng"] - cx)
    g = g.assign(_angle=angles).sort_values("_angle").drop(columns=["_angle"])
    if len(g) < 3:
        return pd.DataFrame(columns=g.columns)
    closed = pd.concat([g, g.iloc[[0]]], ignore_index=True)
    closed["is_close_vertex"] = False
    closed.iloc[-1, closed.columns.get_loc("is_close_vertex")] = True
    return closed


def build_ordered_zone_polygons(zone_detail_df: pd.DataFrame) -> pd.DataFrame:
    """Apply order_and_close_ring to every zone in a zone_detail dataframe."""
    return (
        zone_detail_df.groupby("zone_id", group_keys=False)
        .apply(order_and_close_ring)
        .reset_index(drop=True)
    )


def build_zone_geodataframe(zone_detail_df: pd.DataFrame, zone_meta_df: pd.DataFrame):
    """Build a GeoDataFrame of zone polygons with material/load metadata attached."""
    if gpd is None:
        raise ImportError("geopandas and shapely are required for build_zone_geodataframe")

    vertices = zone_detail_df[["zone_id", "lat", "lng"]].dropna()
    polygons = [
        {"zone_id": zid, "geometry": Polygon(g[["lng", "lat"]].values)}
        for zid, g in vertices.groupby("zone_id")
        if len(g) > 2
    ]
    zone_gdf = gpd.GeoDataFrame(polygons, crs="EPSG:4326")
    meta_cols = ["id", "label", "zone_material_type", "zone_load_type"]
    return zone_gdf.merge(zone_meta_df[meta_cols], left_on="zone_id", right_on="id", how="left")


def zone_diameter_stats(zones_gdf) -> pd.DataFrame:
    """Per-zone bounding-box diagonal in meters — used to pick a DBSCAN eps
    that's small relative to real zone size (so stop-clusters don't spill
    across adjacent zones).
    """
    from . import routes

    rows = []
    for _, z in zones_gdf.iterrows():
        minx, miny, maxx, maxy = z["geometry"].bounds
        rows.append({
            "zone_id": z["zone_id"],
            "label": z.get("label"),
            "zone_material_type": z.get("zone_material_type"),
            "diameter_m": routes.haversine(minx, miny, maxx, maxy),
        })
    return pd.DataFrame(rows).sort_values("diameter_m").reset_index(drop=True)


def zone_ping_density(gps_df: pd.DataFrame, zones_gdf, speed_col: str = "speed",
                       speed_threshold: float = 2.0) -> pd.DataFrame:
    """Count of low-speed/stopped GPS pings falling inside each zone polygon.

    A QA check for whether mine-drawn zone polygons line up with where
    trucks actually stop: zones with ~0 stopped pings despite being labeled
    load/dump/fuel/repair are candidates for stale or mis-drawn geometry.
    """
    stopped = gps_df[gps_df[speed_col] < speed_threshold] if speed_col in gps_df.columns else gps_df
    hits = assign_zone_hit(stopped, zones_gdf)
    counts = hits.groupby("zone_id_hit").size().rename("n_stopped_pings")

    out = zones_gdf[["zone_id", "label", "zone_material_type", "zone_load_type"]].merge(
        counts, left_on="zone_id", right_index=True, how="left"
    )
    out["n_stopped_pings"] = out["n_stopped_pings"].fillna(0).astype(int)
    return out.sort_values("n_stopped_pings").reset_index(drop=True)


def assign_zone_hit(gps_df: pd.DataFrame, zones_gdf) -> pd.DataFrame:
    """For each GPS ping, find which zone polygon (if any) it falls inside.

    Uses a spatial join (sjoin) against zones_gdf's spatial index rather
    than a per-row polygon scan — needed to run on fleet-scale (1M+ ping)
    datasets in reasonable time. If a ping falls inside more than one
    overlapping zone, the first match is kept.
    """
    if gpd is None:
        raise ImportError("geopandas and shapely are required for assign_zone_hit")

    df = gps_df.reset_index(drop=True)
    points = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df["lng"], df["lat"]), crs=zones_gdf.crs,
    )
    joined = gpd.sjoin(
        points,
        zones_gdf[["zone_id", "zone_material_type", "zone_load_type", "geometry"]],
        how="left", predicate="within",
    )
    joined = joined[~joined.index.duplicated(keep="first")].sort_index()

    out = df.copy()
    out["zone_id_hit"] = joined["zone_id"].values
    out["zone_mat_hit"] = joined["zone_material_type"].values
    out["zone_load_hit"] = joined["zone_load_type"].values
    return out
