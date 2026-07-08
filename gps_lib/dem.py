"""SRTM DEM download, unzip, merge, and sampling utilities."""
import glob
import gzip
import math
import os
import shutil
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.merge import merge

from . import routes


def download_srtm_tile(lat: int, lng: int, save_dir: str) -> Optional[Path]:
    """Download one 1x1 degree SRTM tile (.hgt.gz) covering (lat, lng)."""
    lat_prefix = "N" if lat >= 0 else "S"
    lng_prefix = "E" if lng >= 0 else "W"
    fname = f"{lat_prefix}{abs(lat):02d}{lng_prefix}{abs(lng):03d}.hgt.gz"
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/skadi/{lat_prefix}{abs(lat):02d}/{fname}"

    os.makedirs(save_dir, exist_ok=True)
    out_path = Path(save_dir) / fname
    print("Downloading:", fname)
    r = requests.get(url)
    if r.status_code != 200:
        print("Failed:", fname, "status:", r.status_code)
        return None
    out_path.write_bytes(r.content)
    print("Saved:", fname)
    return out_path


def download_srtm_coverage(min_lat: float, max_lat: float, min_lng: float, max_lng: float,
                            save_dir: str) -> List[Path]:
    """Download all SRTM tiles covering a lat/lng bounding box."""
    downloaded = []
    for lat in range(math.floor(min_lat), math.floor(max_lat) + 1):
        for lng in range(math.floor(min_lng), math.floor(max_lng) + 1):
            tile = download_srtm_tile(lat, lng, save_dir)
            if tile:
                downloaded.append(tile)
    return downloaded


def unzip_tiles(tile_dir: str) -> List[str]:
    """Unzip every .hgt.gz in tile_dir to .hgt alongside it."""
    extracted = []
    for gz in glob.glob(f"{tile_dir}/*.gz"):
        hgt = gz.replace(".gz", "")
        with gzip.open(gz, "rb") as f_in, open(hgt, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        extracted.append(hgt)
    return extracted


def merge_dem_tiles(tile_dir: str, out_path: str) -> str:
    """Merge all .hgt tiles in tile_dir into a single GeoTIFF."""
    hgt_files = glob.glob(f"{tile_dir}/*.hgt")
    srcs = [rasterio.open(f) for f in hgt_files]
    try:
        mosaic, transform = merge(srcs)
        meta = srcs[0].meta.copy()
        meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": transform,
            "crs": "EPSG:4326",
        })
        with rasterio.open(out_path, "w", **meta) as dst:
            dst.write(mosaic)
    finally:
        for s in srcs:
            s.close()
    return out_path


def sample_elevation(dem_path: str, lats, lngs) -> np.ndarray:
    """Sample elevation (m) from a merged DEM raster at the given (lat, lng) points."""
    with rasterio.open(dem_path) as src:
        return np.array([v[0] for v in src.sample(zip(lngs, lats))], dtype=float)


def add_segment_grade(dem_path: str, points_df: pd.DataFrame) -> pd.DataFrame:
    """Add elevation and grade (%) since the previous point along a route's
    points, for grade/slope as a haul-segment travel-time covariate
    (Section 4.5 — loaded uphill vs. empty downhill).

    points_df must be sorted in trajectory order (e.g. one tracker's pings
    sorted by get_time).
    """
    df = points_df.reset_index(drop=True).copy()
    df["elevation_m"] = sample_elevation(dem_path, df["lat"].values, df["lng"].values)

    dz = df["elevation_m"].diff()
    dist_m = routes.haversine(df["lng"].shift(), df["lat"].shift(), df["lng"], df["lat"])
    df["grade_pct"] = (dz / dist_m.replace(0, np.nan)) * 100
    return df
