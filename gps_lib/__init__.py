"""Shared library for the open-pit mine GPS project.

Modules are organized by purpose; notebooks under notebooks/api/ and
notebooks/analysis/ import from here instead of redefining logic locally.

- config       : environment/credentials loading (.env)
- navixy_api   : Navixy-style tracking API client (auth, tracker/zone/track endpoints)
- io_utils     : CSV read/write against the configured data directory
- classify     : label-based classification rules for trackers and zones
- preprocess   : GPS ping cleaning and time/technic filtering
- zones        : zone polygon construction and point-in-zone lookups
- routes       : zone-to-zone route extraction and per-route metrics
- clustering   : KMeans + DBSCAN helpers for point/route-shape/stop clustering
- stops        : DBSCAN stop detection, zone labeling, unplanned-idle share, sensitivity sweep
- cycles       : full round-trip haul-cycle extraction, metrics, and plots
- cycle_classification : haul-cycle extraction, phase decomposition, segment classification
- dem          : SRTM elevation tile download/merge/sampling and grade computation
- plotting     : all matplotlib/seaborn visualizations
"""
