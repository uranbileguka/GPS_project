"""Zone-to-zone route extraction and per-route shape/timing metrics."""
from typing import List, Optional

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point


def haversine(lon1, lat1, lon2, lat2):
    R = 6371000
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def extract_routes(gps_hits_df: pd.DataFrame, start_material: str, start_load: str,
                    end_material: str, end_load: str) -> List[dict]:
    """Segment each tracker's pings into routes between two zone types.

    e.g. start_material='middling', start_load='load', end_material='reject',
    end_load='unload' reproduces the "middling load -> big reject dump" route
    definition used in the original route-clustering notebook.
    """
    routes = []
    for tid, g in gps_hits_df.groupby("tracker_id"):
        g = g.sort_values("get_time")
        in_route, seg = False, []
        for _, r in g.iterrows():
            mat, load = r["zone_mat_hit"], r["zone_load_hit"]
            if not in_route:
                if mat == start_material and load == start_load:
                    in_route, seg = True, [r]
            else:
                seg.append(r)
                if mat == end_material and load == end_load:
                    routes.append({
                        "tracker_id": tid,
                        "start_time": seg[0]["get_time"],
                        "end_time": r["get_time"],
                        "points": seg.copy(),
                    })
                    in_route, seg = False, []
    return routes


def resample_route(points, n: int = 100) -> np.ndarray:
    """Resample a route's points to a fixed-length (lng, lat) vector for shape clustering."""
    line = LineString([(p["lng"], p["lat"]) for p in points])
    distances = np.linspace(0, line.length, n)
    return np.array([(s.x, s.y) for s in (line.interpolate(d) for d in distances)])


def route_distance(points) -> float:
    return sum(
        haversine(points[i - 1]["lng"], points[i - 1]["lat"], points[i]["lng"], points[i]["lat"])
        for i in range(1, len(points))
    )


def route_duration(points) -> float:
    t0, t1 = pd.to_datetime(points[0]["get_time"]), pd.to_datetime(points[-1]["get_time"])
    return (t1 - t0).total_seconds()


def route_tortuosity(points) -> float:
    dist = route_distance(points)
    straight = haversine(points[0]["lng"], points[0]["lat"], points[-1]["lng"], points[-1]["lat"])
    return 1 if straight == 0 else dist / straight


def compute_stops(points, speed_threshold: float = 0.5) -> int:
    stops = 0
    for i in range(1, len(points)):
        p1, p2 = points[i - 1], points[i]
        dt = (pd.to_datetime(p2["get_time"]) - pd.to_datetime(p1["get_time"])).total_seconds()
        if dt <= 0:
            continue
        speed = haversine(p1["lng"], p1["lat"], p2["lng"], p2["lat"]) / dt
        if speed < speed_threshold:
            stops += 1
    return stops


def route_noise(points) -> float:
    """Sum of absolute turning angles along the route (higher = more zig-zag)."""
    angles = []
    for i in range(1, len(points) - 1):
        p0, p1, p2 = points[i - 1], points[i], points[i + 1]
        v1 = np.array([p1["lng"] - p0["lng"], p1["lat"] - p0["lat"]])
        v2 = np.array([p2["lng"] - p1["lng"], p2["lat"] - p1["lat"]])
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm == 0:
            continue
        angles.append(np.arccos(np.clip(np.dot(v1, v2) / norm, -1, 1)))
    return float(np.sum(np.abs(angles)))


def passes_through_polygons(points, polygons) -> bool:
    return any(Point(p["lng"], p["lat"]).within(poly) for p in points for poly in polygons)


def summarize_routes(routes: List[dict], small_reject_polys: Optional[list] = None) -> pd.DataFrame:
    """Build the per-route metrics table (distance, duration, tortuosity, stops, noise, cluster)."""
    rows = []
    for idx, r in enumerate(routes):
        pts = r["points"]
        row = {
            "route_idx": idx,
            "tracker_id": r["tracker_id"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "duration_sec": route_duration(pts),
            "distance_m": route_distance(pts),
            "tortuosity": route_tortuosity(pts),
            "num_stops": compute_stops(pts),
            "noise_index": route_noise(pts),
            "cluster": r.get("cluster"),
        }
        if small_reject_polys is not None:
            row["passes_small_reject"] = passes_through_polygons(pts, small_reject_polys)
        rows.append(row)
    return pd.DataFrame(rows)
