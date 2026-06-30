# GPS_project

GPS-based fleet analytics for an open-pit mine: tracker/zone data pulled from
a Navixy-style tracking API, cleaned and joined to mine zone polygons, and
analyzed for tracker paths, zone-to-zone haul routes, route clustering, and
elevation/grade context.

## Layout

```
gps_lib/                    shared functions, organized by purpose
  config.py                   .env loading (credentials, data dir)
  navixy_api.py                API client: auth, tracker/zone/track endpoints
  io_utils.py                  CSV read/write against the configured data dir
  classify.py                  label-based rules: technic_type, zone_material_type, zone_load_type
  preprocess.py                GPS ping cleaning, time filtering, technic join
  zones.py                     zone polygon construction + point-in-zone lookups
  routes.py                    zone-to-zone route extraction + per-route metrics
  clustering.py                KMeans helpers for point/route-shape clustering
  dem.py                       SRTM elevation tile download/merge
  plotting.py                  all visualizations

notebooks/
  api/                       pull data from the Navixy API (writes to data/)
    fetch_tracker_list.ipynb    tracker/vehicle metadata refresh
    fetch_gps_tracks.ipynb      GPS point history pull for a date range
    fetch_zones.ipynb           zone list + zone polygon vertices
  analysis/                  read from data/, no API calls
    trackpoint_analysis.ipynb     clean + plot tracker paths, zone overlay
    zone_analysis.ipynb           zone classification + polygon visualization
    route_clustering_analysis.ipynb  zone-hit assignment, route extraction, KMeans clustering
    dem_analysis.ipynb            elevation tile download/merge/visualize

data/                       not committed to git (see .gitignore) — either
                             populate it by running the notebooks/api/
                             notebooks, or point GPS_DATA_DIR (see below) at
                             an existing copy.
```

Every notebook's first code cell does `sys.path.append("../..")` and then
imports only the `gps_lib` functions it needs — no function is defined more
than once across the project.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and fill in NAVIXY_LOGIN / NAVIXY_PASSWORD
```

`.env` is gitignored — real credentials never get committed. `.env.example`
documents which variables are needed.

By default `data/` resolves to the repo-local `data/` directory. If you'd
rather not duplicate large GPS CSVs / DEM tiles, set `GPS_DATA_DIR` in `.env`
to point at an existing data folder instead:

```
GPS_DATA_DIR=/path/to/existing/data
```

## Typical workflow

1. `notebooks/api/fetch_tracker_list.ipynb` — refresh `tracker_list.csv`
2. `notebooks/api/fetch_zones.ipynb` — refresh `zone_list.csv` / `zone_detail_all_df.csv`
3. `notebooks/api/fetch_gps_tracks.ipynb` — pull GPS pings for a date range (edit the parameters cell first)
4. Any notebook under `notebooks/analysis/` — these only read from `data/`, no API calls or credentials needed
