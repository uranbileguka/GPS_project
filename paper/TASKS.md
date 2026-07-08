# Task List — Trajectory Clustering / Cycle Time / Idle Detection Paper

Tracks work needed to take `draft_paper.md` from outline to submittable draft.

## A. Data engineering (do first — everything else depends on it)
- [x] Consolidate `gps_data.csv` + monthly files into one cleaned dataset — `io_utils.load_gps_data()` now concatenates every `gps_data_<year>-<month>.csv`. The `gps_data_2025-7.csv` `parking`/`alt` column-order mismatch is a non-issue: `pd.concat` aligns by column *name*, not position, so it doesn't need a manual fix.
- [x] Deduplicate pings, parse timestamps, sort by `tracker_id, get_time` — **done**: `preprocess.clean_gps_points()` now sorts by `["tracker_id","get_time"]` after parsing. Centralized in `gps_lib/preprocess.py`.
- [x] Compute per-ping `dt` (sec since last ping) and `dist` (haversine) per tracker; flag implausible-speed jumps — **done**: `preprocess.add_motion_features()` adds `dt`, `dist`, `speed_kmh`, `implausible_jump`. Run result: 0.04% (9,644) pings flagged as implausible and dropped.
- [x] QA pass on `zone_list.csv` polygons — **done**: `zones.zone_ping_density()` and `zones.zone_diameter_stats()` implemented; QA notebook at `notebooks/analysis/data_qa.ipynb`. Zones range 285–2969 m diameter (median 429 m).
- [x] Decide eps/min_samples for DBSCAN — **done**: recommended eps = 107 m (median zone diameter / 4 = 429 / 4). `clustering.dbscan_cluster_stops()` implemented with haversine metric and ball_tree algorithm.

## B. Site/dispatch data request (parallel track, not blocking GPS-only analysis)
- [ ] Send the data request from our last conversation to the mine site contact: payload-per-cycle, fuel logs/sensor feed, truck spec sheet (see prior message for exact field list).
- [ ] If dispatch logs arrive, write a join script keyed on `tracker_id` + nearest timestamp to merge into the GPS-derived cycle table.

## C. Methodology implementation — COMPLETE
- [x] Build stop-detection DBSCAN pipeline (Section 4.2) — **done**: `gps_lib/clustering.py` now has `dbscan_cluster_stops(coords, eps_m, min_samples)` using haversine metric + ball_tree. `gps_lib/stops.py` (new) wraps it with `filter_stop_pings`, `cluster_and_label_stops`, `unplanned_idle_share`, `dbscan_sensitivity_sweep`.
- [x] Label DBSCAN clusters by zone overlap — **done**: `stops.cluster_and_label_stops()` computes cluster centroids and spatial-joins them to `zones_gdf` via `zones.assign_zone_hit()`.
- [x] Implement cycle extraction (Section 4.3) — **done**: `gps_lib/cycles.py` (new) has `extract_cycles` (load→dump→load by zone_load_hit), `decompose_cycle` (4-phase decomposition with multi-dump-visit support), `cycles_to_dataframe`.
- [x] Implement segment classifier (Section 4.4) — **done**: `cycles.classify_segments()` tags each ping as transit / operating / queuing / unplanned_idle; `cycles.state_time_breakdown()` computes dt-weighted % per state.
- [x] Pull DEM grade along haul segment — **done**: `dem.sample_elevation()` and `dem.add_segment_grade()` added; grade computed as elevation_diff / haversine_dist × 100.
- [x] DBSCAN sensitivity sweep — **done**: `stops.dbscan_sensitivity_sweep()` implemented; sensitivity analysis included in `notebooks/analysis/cycle_idle_analysis.ipynb`.

## D. Analysis / results — COMPLETE
- [x] Fleet-wide time-state breakdown — **done**: unplanned_idle 50.2%, transit 44.2%, operating 5.1%, queuing 0.5% (19.3M pings, 89 dump trucks, Jul–Nov 2025).
- [x] Cycle time distributions — **done**: 126,357 cycles extracted. Median cycle 26.5 min (load dwell 4.1, haul-to-dump 7.2, dump dwell 6.9, haul-to-load 4.9 min).
- [x] Identify bottleneck zones — **done**: zone diameter stats show BN circuit load zones (1051–1456 m) are largest; stop-ping breakdown by zone type available in `cycle_idle_analysis.ipynb`.
- [x] Monthly trend — **done**: Sep 2025 worst (57.5% idle, 38.1% transit); Oct–Nov best (46.2–46.4% idle). See Table 3 in Results.
- [x] Validate cycles visually — `plotting.plot_zones_with_tracker_paths` in use in `trackpoint_analysis.ipynb`.

## E. Writing
- [x] Fill in Results (Section 5) — **done**: Sections 5.1–5.6 written with real numbers from pipeline run. Tables 1–3 filled.
- [x] Write Abstract — **done**: ~230-word abstract with headline numbers (50.2% idle, 126,357 cycles, 26.5 min median cycle).
- [x] Write Conclusion — **done**: Section 7 with three concrete operational recommendations (zone polygon coverage, dispatch scheduling review, GPS-only diagnostic baseline).
- [ ] Decide target venue — options: *Mining, Metallurgy & Exploration* (applied, suits the case-study format), *International Journal of Mining, Reclamation and Environment* (environmental/operational focus), or *IISE Annual Conference* (closest precedent: Priegnitz & Yoo [4]). Recommend MME first given Fan et al. [1] published there on a closely adjacent topic.
- [ ] Advisor/mine-engineering review of cycle/zone definitions in Section 4 — still needed before submission. Priority item.

## F. Optional extensions (only if B succeeds)
- [ ] Add payload-normalized productivity (tonnes/cycle-hour) once dispatch data is joined.
- [ ] Add fuel-cost-of-idle estimate once fuel data is joined — this is usually the number that gets management attention, worth prioritizing if any one extension is pursued.
