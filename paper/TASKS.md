# Task List — Trajectory Clustering / Cycle Time / Idle Detection Paper

Tracks work needed to take `draft_paper.md` from outline to submittable draft.

## A. Data engineering (do first — everything else depends on it)
- [x] Consolidate `gps_data.csv` + monthly files into one cleaned dataset — `io_utils.load_gps_data()` now concatenates every `gps_data_<year>-<month>.csv`. The `gps_data_2025-7.csv` `parking`/`alt` column-order mismatch is a non-issue: `pd.concat` aligns by column *name*, not position, so it doesn't need a manual fix.
- [ ] Deduplicate pings, parse timestamps, sort by `tracker_id, get_time` — `preprocess.clean_gps_points()` dedups and parses `get_time`, but sorting by `tracker_id, get_time` is still done ad hoc per-notebook (e.g. `route_clustering_analysis.ipynb`), not centralized in `gps_lib`.
- [ ] Compute per-ping `dt` (sec since last ping) and `dist` (haversine) per tracker; flag implausible-speed jumps. **Not implemented** — `routes.py` only has route-level `route_distance`/`route_duration`, not per-ping.
- [ ] QA pass on `zone_list.csv` polygons against actual GPS density (do trucks actually cluster inside the drawn polygons, or are some zones mis-drawn/outdated?). **Not started.**
- [ ] Decide eps/min_samples search range for DBSCAN based on actual zone polygon sizes (compute typical zone diameter from `zone_detail_all_df.csv`). **Not started** — no DBSCAN code exists yet (see C).

## B. Site/dispatch data request (parallel track, not blocking GPS-only analysis)
- [ ] Send the data request from our last conversation to the mine site contact: payload-per-cycle, fuel logs/sensor feed, truck spec sheet (see prior message for exact field list).
- [ ] If dispatch logs arrive, write a join script keyed on `tracker_id` + nearest timestamp to merge into the GPS-derived cycle table.

## C. Methodology implementation — NOT STARTED, this is the core of the paper and the current blocker
- [ ] Build stop-detection DBSCAN pipeline (Section 4.2) — `clustering.py` currently only has K-means (`kmeans_cluster_points`, `kmeans_cluster_route_shapes`); add a `dbscan_cluster_stops()` alongside it rather than replacing the K-means route-shape work (the paper explicitly contrasts the two in Methods).
- [ ] Label DBSCAN clusters by zone overlap; quantify the share of stops that fall outside any surveyed zone (unplanned idle). Can reuse `zones.assign_zone_hit()`.
- [ ] Implement cycle extraction (Section 4.3): load-zone stop → dump-zone stop → load-zone stop, with phase decomposition. **Not implemented** — `routes.extract_routes()` does zone-to-zone segmentation for K-means route shapes, but not load→dump→load cycle detection with phase splits.
- [ ] Implement segment classifier (Section 4.4): transit / queuing / operating / unplanned-idle. **Not implemented.**
- [ ] Pull DEM grade along each haul segment — `dem.py` has `download_srtm_coverage`/`unzip_tiles`/`merge_dem_tiles` (the raster is built), but there's no sampling-along-route-line function yet.
- [ ] Run DBSCAN parameter sensitivity sweep; log how cycle count / idle % shifts.

## D. Analysis / results
- [ ] Fleet-wide time-state breakdown (transit/queue/operate/idle) with CIs. Blocked on C.
- [ ] Cycle time distributions by truck and by load↔dump zone pair. Blocked on C.
- [ ] Identify top bottleneck load zones (highest queue dwell). Blocked on C.
- [ ] Map unplanned-idle hotspots. Blocked on C.
- [ ] Trend state-time breakdown across Jul–Nov 2025 (day-of-week, shift). Blocked on C.
- [x] Validate a sample of detected cycles visually — `plotting.plot_zones_with_tracker_paths` exists and is in use in `trackpoint_analysis.ipynb`; re-apply once C produces real cycles.

## E. Writing
- [ ] Fill in Results (Section 5) from D above — replace all numeric placeholders.
- [ ] Write Abstract last, once headline numbers exist.
- [ ] Write Conclusion with concrete recommendation tied to the biggest bottleneck found.
- [ ] Decide target venue (mining engineering journal vs. GIS/spatial-analytics journal vs. conference) — affects formatting, length limits, and whether queuing-theory (Section 2) or ML-comparison (vs. Fan et al. [1], Zhao et al. [7]) framing should be emphasized.
- [ ] Have an advisor/mine-engineering reader sanity-check the cycle/zone definitions in Section 4 before running full analysis — cheaper to fix definitions now than to rerun after Results are written.

## F. Optional extensions (only if B succeeds)
- [ ] Add payload-normalized productivity (tonnes/cycle-hour) once dispatch data is joined.
- [ ] Add fuel-cost-of-idle estimate once fuel data is joined — this is usually the number that gets management attention, worth prioritizing if any one extension is pursued.
