"""Clustering helpers for trajectory points and route shapes."""
import numpy as np
from sklearn.cluster import DBSCAN, KMeans

EARTH_RADIUS_M = 6371000.0


def kmeans_cluster_points(coords: np.ndarray, k: int = 6, random_state: int = 0) -> np.ndarray:
    """Cluster raw (lng, lat) points — a first-pass spatial grouping of GPS pings."""
    model = KMeans(n_clusters=k, random_state=random_state, n_init="auto")
    return model.fit_predict(coords)


def kmeans_cluster_route_shapes(route_vectors: np.ndarray, k: int = 6, random_state: int = 42) -> np.ndarray:
    """Cluster resampled route-shape vectors (output of routes.resample_route)."""
    model = KMeans(n_clusters=k, random_state=random_state)
    return model.fit_predict(route_vectors)


def dbscan_cluster_stops(coords: np.ndarray, eps_m: float = 30.0, min_samples: int = 3) -> np.ndarray:
    """Cluster stationary GPS pings by location with DBSCAN (haversine metric).

    coords: array of [lat, lng] in degrees. eps_m: cluster radius in meters.
    Returns cluster labels per point; -1 means noise (not part of any
    dense stop cluster).
    """
    coords_rad = np.radians(coords)
    eps_rad = eps_m / EARTH_RADIUS_M
    model = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine", algorithm="ball_tree")
    return model.fit_predict(coords_rad)
