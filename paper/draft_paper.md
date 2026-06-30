# Trajectory Clustering, Cycle Time, and Idle Detection for Open-Pit Haul Truck Fleets: A GPS-Based Case Study

*Draft v0.1 — working title, not final*

## Abstract

*(write last — ~200 words once Results are filled in)*
Open-pit haulage efficiency is dominated by non-productive time: queuing at shovels, idling between cycles, and excess dwell at dump/load points. This study uses raw GPS telemetry from a fleet of dump trucks and loaders at an open-pit coal mine (Tsogttsetii district, South Gobi, Mongolia) to (1) identify stationary/low-speed clusters via DBSCAN, (2) extract truck cycle times between loading and dumping events, (3) classify trajectory segments into transit, queuing, and operating states, and (4) quantify operational inefficiency using mine-defined functional zones. We report [X]% of fleet time spent idle/queuing versus transit, identify the [N] highest-inefficiency zone pairs, and discuss implications for dispatch scheduling.

---

## 1. Introduction

- Open-pit mine productivity is bottlenecked by truck-shovel cycle efficiency; even small reductions in idle/queue time compound across a fleet operating 24/7.
- GPS/telematics data is now collected by default on most haul fleets, but is frequently used only for live tracking, not systematic cycle/idle analytics.
- This paper asks: **can unsupervised trajectory clustering, applied directly to raw positional pings (no payload or fuel sensors required), reliably recover cycle structure and quantify idle/queue inefficiency at a working mine?**
- Contributions:
  1. A DBSCAN-based pipeline for stop/queue detection validated against mine-surveyed zone polygons (loading, dumping, fuel, repair, parking) rather than purely unsupervised cluster labels.
  2. A cycle-time extraction method tied to truck type (`tracker_list.technic_type`: dump vs. loader) so haul cycles and loading-equipment cycles are analyzed separately.
  3. A segment classification scheme (transit / queuing / operating) usable for fleet-level inefficiency reporting.
  4. A real operational case study at a Mongolian open-pit coal mine — a geographic/operational context underrepresented in the mining-analytics literature, which is dominated by Australian, Chilean, and Polish case sites.

## 2. Related Work

| Theme | Key prior work | Relevance / gap this paper addresses |
|---|---|---|
| DBSCAN for haul truck cycle/stop identification | Gawelski, Jachnik, Stefaniak & Skoczylas (2020) — SVM + DBSCAN cycle identification on KGHM Lubin underground haul trucks [3] | Prior DBSCAN work is underground (no GPS, uses onboard hydraulic/CAN signals); we apply the same density-clustering idea to **open-pit GPS positional data**, a different and noisier signal source. |
| Spatial clustering for truck location/state classification | Priegnitz & Yoo (2019), *Automated Location Classification of Mining Trucks from GPS Data*, IISE Annual Conf. [4] | Closest prior work — DBSCAN directly on mine-truck GPS to classify queue/shovel locations. We extend this by tying clusters to **labeled zone polygons** already maintained by the mine (loading/dump/fuel/repair), enabling validation rather than relying on cluster shape alone. |
| Spatiotemporal trajectory segmentation | Chen, Ji & Wang (2014), T-DBSCAN [6] | Standard DBSCAN ignores the time-sequential structure of a trajectory (revisits to the same place at different times collapse into one cluster). We discuss whether T-DBSCAN-style time-aware clustering is needed once mileage/heading is added as a feature. |
| ML cycle-time prediction | Fan, Zhang, Jiang et al. (2025), feature-optimized XGBoost cycle-time estimation [1]; Zhao, Gao & Ren (2025), LSTM-TabTransformer travel-time prediction [7] | These are **supervised/predictive** approaches requiring dispatch-system ground truth (shovel ID, loaded/empty state) we do not currently have. Our paper is explicitly the unsupervised, GPS-only predecessor — a contribution in its own right when dispatch data is unavailable, and a baseline these methods could later improve on once dispatch logs are obtained. |
| Underground cycle detection via neural nets | Skoczylas, Rot, Stefaniak & Śliwiński (2023), Sensors [5] | Confirms the 4-phase cycle model (load → haul-full → dump → haul-empty) we adopt, but for underground LHDs; we test whether the same phase model transfers to open-pit dump trucks. |
| Queuing theory for shovel-truck systems | Kaungu, Githiria, Mutua & Dalmus (2021), Arabian J. Geosciences [8] | Provides the theoretical idle/queue framing (M/M/c-style waiting analysis) we use to interpret empirical queue-dwell distributions at loading zones. |
| Cycle/idle detection methods, broadly | *Operational Cycle Detection for Mobile Mining Equipment: An Integrative Scoping Review*, Eng (2025) [2] | A 2025 scoping review of 20 empirical cycle-detection studies (19 diesel fleets, 1 BEV) — used to position our method choice (DBSCAN on raw GPS vs. CAN-bus/hydraulic-signal methods dominant in the reviewed literature) and to justify GPS-only analysis as a lower-cost, retrofit-free alternative. |

**Gap this paper fills:** almost all DBSCAN/ML cycle-detection literature assumes either (a) underground haul trucks with rich onboard sensor streams, or (b) open-pit trucks with a dispatch/FMS system providing payload and shovel-assignment ground truth. This study sits in the realistic middle case most small/mid-size open-pit operations actually have: **bare GPS pings + a hand-maintained zone map**, nothing else. The method needs to be robust to that constraint, and the paper should be explicit about what that constraint costs in interpretability (Section 6, Limitations).

## 3. Study Site and Data

**Site:** Open-pit coal mine, Tsogttsetii district (Цогтцэций сум), Ömnögovi (South Gobi) Province, Mongolia. Pit features include multiple stockpile zones (овоолго), a "reject" loading/unloading area, a processing/beneficiation plant (Баяжуулах үйлдвэр), a fuel point, repair shop, and worker camp.

**Datasets** (all in `data/`):

| File | Description | Use in this study |
|---|---|---|
| `gps_data.csv`, `gps_data_2025-{7,8,9,10,11}.csv` | Raw GPS pings: `tracker_id, get_time, lat, lng, speed, heading, alt, mileage(odometer km), satellites, parking(bool), address` | Primary trajectory data; ~2.5GB across 5 months, ~10s–30s ping interval |
| `tracker_list.csv` | 123 vehicles: `id, label, technic_type(dump/loader/other), group_id, ...` | Truck/loader identity, fleet segmentation |
| `zone_list.csv` + `zone_detail_all_df.csv` | 104 mine-surveyed functional zones (polygon/circle geometries): loading, dumping/stockpile, fuel, repair, parking, plant | Ground-truth labels to validate DBSCAN clusters and define cycle endpoints |
| `dem_merged.tif` + `dem_tiles/` | SRTM-derived elevation raster covering the pit | Grade/slope covariate for haul-segment travel time (loaded uphill vs. empty downhill) |

**Not available** (see Section 6 / Appendix A task list): truck payload per cycle, fuel consumption, dispatch/shovel-assignment logs, material type per haul.

**Preliminary work already completed** (`analysis/` notebooks, to be folded into Methods):
- `GPS_zone_analysis.ipynb`: zone polygons parsed and labeled by material/load type (load vs. unload) from zone names.
- `GPS_trackpoint_route_analysis.ipynb`: GPS points spatially joined to zone polygons; truck paths segmented into zone-to-zone "routes"; route shape features computed (distance, duration, tortuosity, stop count, heading-noise index); **K-means (k=6)** applied to resampled route vectors as a first-pass route-shape clustering (distinct from the DBSCAN stop-clustering proposed for this paper — worth contrasting the two in Methods).
- `dem_data_get.ipynb`: SRTM tiles downloaded and merged into a single DEM raster covering the GPS bounding box, ready for elevation/grade lookups.

## 4. Methodology

### 4.1 Preprocessing
- Deduplicate pings, parse `get_time`, sort per `tracker_id`.
- Compute per-ping `dt` (seconds since previous ping) and `dist` (haversine distance from previous ping) per tracker; flag/drop pings with implausible jumps (GPS glitches) using a max-speed threshold.
- Restrict to `technic_type == 'dump'` for haul-cycle analysis; analyze `loader` trucks separately (their cycle structure is fundamentally different — stationary loading vs. mobile hauling).

### 4.2 Stop / stationary-cluster detection (DBSCAN)
- Filter pings to low-speed (`speed < threshold`, e.g. 1–2 km/h) or `parking == True`.
- Run DBSCAN per truck (or per fleet, with truck ID as an extra non-spatial dimension) on `(lat, lng)` with `eps` and `min_samples` tuned against known zone polygon sizes (cf. Priegnitz & Yoo's eps=100m precedent [4] — to be tuned, not copied, given this pit's tighter zone geometry).
- Label each resulting cluster by spatial overlap with `zone_list`/`zone_detail_all_df` polygons (load zone, dump zone, fuel, repair, parking, "unlabeled stop").
- Where stops fall outside any surveyed zone, treat as **unplanned/road-side idle** — itself a finding worth reporting (these are the "invisible" inefficiencies a zone-only analysis would miss).

### 4.3 Cycle time extraction
- For each dump truck, define a cycle as: `loading-zone stop → haul (full) → dump-zone stop → haul (empty) → back to loading-zone stop`.
- Cycle time = `t(arrive at next load-zone stop) − t(arrive at previous load-zone stop)`; decompose into load-zone dwell, haul-to-dump transit, dump-zone dwell, haul-to-load transit.
- Cross-check decomposition against the 4-phase model used for underground LHDs in Skoczylas et al. [5] — confirm it transfers to open-pit dump-truck cycles, or document where it doesn't (e.g., multiple dump visits per load due to partial loads).

### 4.4 Segment classification: transit / queuing / operating
- **Operating**: inside a load or dump zone polygon, low speed, with the expected loader-interaction pattern (brief stop, not full shutdown).
- **Queuing**: stopped/low-speed, near (buffer distance around) a load-zone polygon but not yet inside the active loading slot — i.e., waiting for the shovel. This is the operational definition that ties directly to the queuing-theory framing in Kaungu et al. [8].
- **Transit**: speed above threshold, heading roughly consistent, outside all zone polygons.
- **Idle (unplanned)**: stopped, outside all known zones, not explained by any of the above (candidate maintenance/breakdown/driver-break events).

### 4.5 Inefficiency quantification
- Per zone (or zone-pair, i.e. load→dump route): mean/median/IQR of queue dwell, operating dwell, and transit time; compare against the theoretical minimum transit time implied by route distance + DEM grade (free-flow baseline).
- Fleet-level KPI: % of total fleet-hours in each state (transit/queue/operate/unplanned-idle) per shift, per day, and trended across the 5-month window — this is the headline efficiency metric of the paper.
- Optional: incorporate DEM-derived grade into expected transit time (steeper loaded-uphill segments should show longer transit even with no inefficiency — important so grade isn't mistaken for queuing).

### 4.6 Validation
- Spot-check a sample of detected cycles against manual inspection of the trajectory plot (already supported by `plot_zones_with_tracker_paths` in `GPS_trackpoint_analysis.ipynb`).
- Sensitivity analysis on DBSCAN `eps`/`min_samples` — report how cycle counts and idle-time estimates change across a reasonable parameter range (this is a common weak point reviewers flag in DBSCAN-based mining papers).

## 5. Results

*(to be filled in once the pipeline in Section 4 is run on the full 5-month dataset — see Appendix A, Task List)*

- [ ] Fleet-wide state-time breakdown (transit/queue/operate/idle), with confidence intervals
- [ ] Cycle time distribution by truck and by load-zone/dump-zone pair
- [ ] Top-N highest-queue-time load zones (candidate shovel bottlenecks)
- [ ] Unplanned-idle hotspot map (stops outside surveyed zones)
- [ ] Day-of-week / shift-level trends across Jul–Nov 2025
- [ ] DBSCAN parameter sensitivity table

## 6. Limitations

- **No payload data**: cycle "productivity" cannot be expressed in tonnes hauled or tonnes/engine-hour — only time-based efficiency. Section on requested dispatch/FMS data (Appendix B) addresses this for a follow-up paper.
- **No fuel data**: idle time cannot be converted to fuel-cost impact, which is usually the number that motivates mine management to act. Flagged as the single highest-value addition if obtainable later.
- **GPS ping interval (~10–30s)** limits precision of short-duration events (brief queue shuffles, exact loader-spotting time).
- **Zone polygons are mine-drawn**, not GPS-derived — possible misalignment between drawn polygon and actual operational footprint (worth a QA pass, see Task List).
- Single-site study — findings on idle/queue proportions are not generalizable without comparison sites.

## 7. Conclusion (draft placeholder)

*(write after Results)* Summarize headline idle/queue percentage, biggest bottleneck zone, and recommend either dispatch-rule changes or specific zone redesigns. Note the GPS-only method as a low-cost diagnostic any open-pit operation with basic GPS tracking can replicate without new sensor investment, and flag the payload/fuel extension as future work.

## References

[1] Fan, C., Zhang, N., Jiang, B., et al. (2025). Rapid Estimation of Truck Cycle Time in Open-Pit Mine Haulage Based on Feature-Optimized Machine Learning. *Mining, Metallurgy & Exploration*, 42, 665–684. https://doi.org/10.1007/s42461-025-01225-0

[2] Operational Cycle Detection for Mobile Mining Equipment: An Integrative Scoping Review with Narrative Synthesis. (2025). *Eng*, 6(10), 279. https://doi.org/10.3390/eng6100279

[3] Gawelski, D., Jachnik, B., Stefaniak, P., & Skoczylas, A. (2020). Haul Truck Cycle Identification Using Support Vector Machine and DBSCAN Models. In *Advances in Computational Collective Intelligence* (ICCCI 2020), CCIS vol. 1287. Springer. https://doi.org/10.1007/978-3-030-63119-2_28

[4] Priegnitz, N., & Yoo, J. J.-W. (2019). Automated Location Classification of Mining Trucks from GPS Data. *IISE Annual Conference Proceedings*, Norcross, 276–281.

[5] Skoczylas, A., Rot, A., Stefaniak, P., & Śliwiński, P. (2023). Haulage Cycles Identification for Wheeled Transport in Underground Mine Using Neural Networks. *Sensors*, 23(3), 1331. https://doi.org/10.3390/s23031331

[6] Chen, W., Ji, M. H., & Wang, J. M. (2014). T-DBSCAN: A Spatiotemporal Density Clustering for GPS Trajectory Segmentation. *International Journal of Online Engineering*, 10(6), 19–24.

[7] Zhao, J., Gao, L., & Ren, S. (2025). Prediction of open-pit mine truck travel time based on LSTM-TabTransformer. *Scientific Reports*, 15. https://doi.org/10.1038/s41598-025-88543-x

[8] Kaungu, E., Githiria, J., Mutua, S., & Dalmus, M. (2021). Optimisation of shovel-truck haulage system in an open pit using queuing approach. *Arabian Journal of Geosciences*, 14(11). https://doi.org/10.1007/s12517-021-07365-z
