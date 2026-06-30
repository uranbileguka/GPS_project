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
    from shapely.geometry import Point, Polygon
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


def assign_zone_hit(gps_df: pd.DataFrame, zones_gdf) -> pd.DataFrame:
    """For each GPS ping, find which zone polygon (if any) it falls inside."""
    if gpd is None:
        raise ImportError("geopandas and shapely are required for assign_zone_hit")

    def _hit(row) -> pd.Series:
        p = Point(row["lng"], row["lat"])
        for _, z in zones_gdf.iterrows():
            if p.within(z["geometry"]):
                return pd.Series({
                    "zone_id_hit": z["zone_id"],
                    "zone_mat_hit": z["zone_material_type"],
                    "zone_load_hit": z["zone_load_type"],
                })
        return pd.Series({"zone_id_hit": None, "zone_mat_hit": None, "zone_load_hit": None})

    df = gps_df.copy()
    df[["zone_id_hit", "zone_mat_hit", "zone_load_hit"]] = df.apply(_hit, axis=1)
    return df
