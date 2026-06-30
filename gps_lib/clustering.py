"""Clustering helpers for trajectory points and route shapes."""
import numpy as np
from sklearn.cluster import KMeans


def kmeans_cluster_points(coords: np.ndarray, k: int = 6, random_state: int = 0) -> np.ndarray:
    """Cluster raw (lng, lat) points — a first-pass spatial grouping of GPS pings."""
    model = KMeans(n_clusters=k, random_state=random_state, n_init="auto")
    return model.fit_predict(coords)


def kmeans_cluster_route_shapes(route_vectors: np.ndarray, k: int = 6, random_state: int = 42) -> np.ndarray:
    """Cluster resampled route-shape vectors (output of routes.resample_route)."""
    model = KMeans(n_clusters=k, random_state=random_state)
    return model.fit_predict(route_vectors)
