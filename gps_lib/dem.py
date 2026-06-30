"""SRTM DEM download, unzip, and merge utilities."""
import glob
import gzip
import math
import os
import shutil
from pathlib import Path
from typing import List, Optional

import rasterio
import requests
from rasterio.merge import merge


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
