# Task List — Trajectory Clustering / Cycle Time / Idle Detection Paper

Tracks work needed to take `draft_paper.md` from outline to submittable draft.

## A. Data engineering (do first — everything else depends on it)
- [ ] Consolidate `gps_data.csv` + monthly files into one cleaned dataset; resolve column-order mismatch (`gps_data_2025-7.csv` has `parking`/`alt` swapped vs. other files — check before concatenating).
- [ ] Deduplicate pings, parse timestamps, sort by `tracker_id, get_time`.
- [ ] Compute per-ping `dt` (sec since last ping) and `dist` (haversine) per tracker; flag implausible-speed jumps.
- [ ] QA pass on `zone_list.csv` polygons against actual GPS density (do trucks actually cluster inside the drawn polygons, or are some zones mis-drawn/outdated?).
- [ ] Decide eps/min_samples search range for DBSCAN based on actual zone polygon sizes (compute typical zone diameter from `zone_detail_all_df.csv`).

## B. Site/dispatch data request (parallel track, not blocking GPS-only analysis)
- [ ] Send the data request from our last conversation to the mine site contact: payload-per-cycle, fuel logs/sensor feed, truck spec sheet (see prior message for exact field list).
- [ ] If dispatch logs arrive, write a join script keyed on `tracker_id` + nearest timestamp to merge into the GPS-derived cycle table.

## C. Methodology implementation
- [ ] Build stop-detection DBSCAN pipeline (Section 4.2) — start from existing zone-join logic in `GPS_trackpoint_route_analysis.ipynb`, replace/extend the K-means route-shape clustering with DBSCAN stop clustering.
- [ ] Label DBSCAN clusters by zone overlap; quantify the share of stops that fall outside any surveyed zone (unplanned idle).
- [ ] Implement cycle extraction (Section 4.3): load-zone stop → dump-zone stop → load-zone stop, with phase decomposition.
- [ ] Implement segment classifier (Section 4.4): transit / queuing / operating / unplanned-idle.
- [ ] Pull DEM grade along each haul segment (`dem_data_get.ipynb` already produces `dem_merged.tif` — add a sampling step along route lines).
- [ ] Run DBSCAN parameter sensitivity sweep; log how cycle count / idle % shifts.

## D. Analysis / results
- [ ] Fleet-wide time-state breakdown (transit/queue/operate/idle) with CIs.
- [ ] Cycle time distributions by truck and by load↔dump zone pair.
- [ ] Identify top bottleneck load zones (highest queue dwell).
- [ ] Map unplanned-idle hotspots.
- [ ] Trend state-time breakdown across Jul–Nov 2025 (day-of-week, shift).
- [ ] Validate a sample of detected cycles visually (use existing `plot_zones_with_tracker_paths`).

## E. Writing
- [ ] Fill in Results (Section 5) from D above — replace all numeric placeholders.
- [ ] Write Abstract last, once headline numbers exist.
- [ ] Write Conclusion with concrete recommendation tied to the biggest bottleneck found.
- [ ] Decide target venue (mining engineering journal vs. GIS/spatial-analytics journal vs. conference) — affects formatting, length limits, and whether queuing-theory (Section 2) or ML-comparison (vs. Fan et al. [1], Zhao et al. [7]) framing should be emphasized.
- [ ] Have an advisor/mine-engineering reader sanity-check the cycle/zone definitions in Section 4 before running full analysis — cheaper to fix definitions now than to rerun after Results are written.

## F. Optional extensions (only if B succeeds)
- [ ] Add payload-normalized productivity (tonnes/cycle-hour) once dispatch data is joined.
- [ ] Add fuel-cost-of-idle estimate once fuel data is joined — this is usually the number that gets management attention, worth prioritizing if any one extension is pursued.
