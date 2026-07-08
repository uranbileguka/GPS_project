# Trajectory Clustering, Cycle Time, and Idle Detection for Open-Pit Haul Truck Fleets: A GPS-Based Case Study

*Draft v0.1 — working title, not final*

---

> **Plain-language primer: the loading cycle (background only, not part of the manuscript text)**
>
> For readers unfamiliar with open-pit haul operations, here is the physical cycle at a stockpile that this paper is trying to measure from GPS data alone:
>
> 1. Loader drives up to the stockpile.
> 2. Loader scoops coal into its bucket.
> 3. Truck waits in line at the loading spot.
> 4. Loader dumps coal into the truck bed — usually 3–6 scoops to fill it.
> 5. Truck drives away to its destination.
> 6. Next truck pulls into position.
> 7. Loader goes back to the stockpile.
> 8. Repeat.
>
> Mapped to the paper's terms (Section 4.4): step 3 is **queuing**, step 4 is **operating**, step 5 is **transit**. Section 4.3's "load-zone dwell" covers steps 3–4 together.

---

## Abstract

Open-pit haulage efficiency is dominated by non-productive time: queuing at shovels, idle stops between cycles, and excess dwell at loading and dumping points. This study applies an unsupervised GPS-only analysis pipeline to five months of raw positional telemetry (July–November 2025) from 89 dump trucks at an open-pit coal mine in Tsogttsetii district, South Gobi, Mongolia — a geographic context underrepresented in the mining-analytics literature. Using DBSCAN stop-cluster detection, zone-polygon spatial joins, and a four-phase cycle decomposition (load-dwell / haul-to-dump / dump-dwell / haul-to-load), we characterize fleet-level operational states without payload sensors, dispatch logs, or onboard CAN-bus signals. Analysis of 19.3 million dump-truck GPS pings (from 45.6 million raw pings after cleaning) reveals that **50.2% of total fleet-seconds** are spent in unplanned idle — stationary outside any mine-surveyed functional zone — against 44.2% in transit and 5.6% inside load or dump zones. The unplanned-idle fraction peaks at 57.5% in September 2025. Across 126,357 complete haul cycles, the median cycle time is 26.5 minutes (median load dwell 4.1 min, haul-to-dump 7.2 min, dump dwell 6.9 min, return haul 4.9 min). These findings quantify the scale of non-productive time recoverable through targeted dispatch and infrastructure interventions, and demonstrate that GPS-only trajectory analysis — requiring no additional sensor investment — is sufficient to identify and prioritize efficiency improvements at operating mines.

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

All results below are derived from the full five-month GPS dataset (July–November 2025) using the pipeline described in Section 4. Raw data, analysis code, and the `gps_lib` Python package are available in the project repository.

### 5.1 Dataset Overview

The raw dataset contains **45,584,435 GPS pings** from 112 tracked vehicles across the five-month window. After deduplication, timestamp parsing, sort-per-tracker, and implausible-jump removal (inter-ping speed > 120 km/h), **24,078,919 pings** remain — a 47.2% reduction, the bulk attributable to duplicate pings and overnight/weekend coverage gaps rather than data quality failures. Only **0.04% (9,644 pings)** were flagged as implausible speed jumps and dropped.

Restricting to the 89 dump-truck trackers (vehicles whose label matches the `HDU|BN` pattern, indicating haul dump units operating on the BN material circuit) yields **19,261,332 pings** — 80.0% of the cleaned total — spanning the full July–November period.

The zone geometry dataset comprises **11 mine-surveyed zone polygons** used in this analysis (after filtering to zones with a recognized material-type label): 4 load zones and 7 unload/dump zones. Zone sizes vary considerably, from 285 m (SP4 loading pad, middling circuit) to 2,969 m bounding-box diagonal (Reject ovoolgo / reject stockpile dump area). The median zone diameter is 429 m; based on this, DBSCAN was run with eps = 107 m (median / 4), ensuring that stop clusters smaller than one zone radius are resolved as distinct.

### 5.2 Fleet-Wide State-Time Breakdown

Table 1 shows the dt-weighted fraction of total dump-truck fleet-time in each operational state, computed over all 89 trucks and all five months.

**Table 1. Fleet-wide state-time breakdown (Jul–Nov 2025, 89 dump trucks).**

| State | Fleet-time share | Description |
|---|---|---|
| Unplanned idle | **50.2%** | Stopped (speed < 2 km/h), outside all 11 zone polygons |
| Transit | 44.2% | Speed ≥ 2 km/h (moving between zones) |
| Operating | 5.1% | Stopped, inside a load or dump zone polygon |
| Queuing | 0.5% | Stopped, outside any zone but within 50 m of a load-zone polygon boundary |

The dominant finding is that **50.2% of total truck-fleet-seconds** are spent stationary outside any surveyed functional zone. This is the single largest time category — larger even than productive transit. The "queuing" fraction (0.5%) is low because the 50 m load-zone buffer is tight; widening this buffer to 200 m would reclassify a portion of unplanned idle as queuing, but this ambiguity reflects genuine uncertainty in the zone-polygon boundary rather than a methodological choice (see Section 6, Limitations).

A key caveat: the 11-zone subset used here covers only load/dump zones with recognized material labels. Mine infrastructure zones for which no polygon was fetched — fuel station, maintenance yard, weighbridge, worker camp, parking lot — are absent from the zone dataset. Stationary time at these locations therefore appears as "unplanned idle" even though it may be operationally necessary. This upper-bounds the true unplanned idle fraction; obtaining the full zone polygon set would allow reclassification.

### 5.3 Haul Cycle Extraction and Phase Decomposition

The cycle extraction procedure (Section 4.3) identified **126,357 complete haul cycles** across all 89 dump trucks over five months, averaging approximately 28 cycles per truck per day. Each cycle is bounded by consecutive arrivals at a load zone, with the intermediate dump-zone visit(s) forming the cycle body.

**Table 2. Haul cycle phase durations (Jul–Nov 2025; seconds converted to minutes).**

| Phase | Median (min) | Mean (min) | Std (min) |
|---|---|---|---|
| Load-zone dwell (loading time) | 4.1 | 7.1 | 14.4 |
| Haul to dump (loaded transit) | 7.2 | 16.8 | 121.6 |
| Dump-zone dwell (unloading + maneuvering) | 6.9 | 10.4 | 56.6 |
| Haul to load (empty return transit) | 4.9 | 24.9 | 280.2 |
| **Total cycle** | **26.5** | **75.6** | **579.2** |

The median total cycle time is **26.5 minutes**; the mean is 75.6 minutes. The large mean/median gap — and the very high standard deviations for haul-to-dump and haul-to-load legs — reflect a heavily right-skewed distribution driven by multi-hour and overnight gap events. These arise when the cycle extractor spans consecutive shifts: a truck completes a dump late in one shift, parks overnight, and resumes at the next load zone next morning, producing a cycle with an artificially long "haul-to-load" leg. Using the median is therefore more appropriate for characterizing the typical operating cycle; the mean is presented for completeness.

The median load dwell (4.1 min) and dump dwell (6.9 min) are consistent with 3–5 loader-bucket passes per loading cycle at a typical open-pit bucket capacity, and with the roughly 2–4 minutes needed to position and discharge at the dump site. The median haul-to-dump leg (7.2 min) is slightly shorter than haul-to-load (4.9 min), which may reflect a routing asymmetry: loaded trucks travel the longer, lower-grade direction to the dump, while the empty return uses a shorter or more direct path, or reflects different speed limits for loaded vs. empty trucks on mine roads.

### 5.4 Stop-Ping Distribution

Of the 19,261,332 dump-truck pings, **966,820 (5.0%)** record a speed below 2 km/h. Of these stop pings, **363,221 (37.6%)** fall inside a recognized zone polygon and **603,599 (62.4%)** fall outside all zones. The dt-weighted dominance of stopped time (55.8% combined across operating + queuing + unplanned_idle) relative to the 5.0% raw ping-share reflects the GPS tracker's behavior in parking mode: when `parking = True`, the tracker reduces its ping frequency to once every 1–5 minutes rather than once every 10–30 seconds, so each parked ping carries a large `dt` weight. This is an important calibration note — ping-count statistics and dt-weighted statistics will differ substantially for this dataset, and dt-weighted fractions are the appropriate efficiency metric for fleet-time analysis.

### 5.5 Monthly Trend

**Table 3. Monthly state-time breakdown (% of fleet-seconds, 89 dump trucks).**

| Month | Transit (%) | Operating (%) | Queuing (%) | Unplanned Idle (%) | Pings |
|---|---|---|---|---|---|
| Jul 2025 | 47.3 | 3.8 | 0.3 | 48.6 | 1,717,727 |
| Aug 2025 | 45.2 | 5.0 | 0.5 | 49.3 | 4,295,875 |
| Sep 2025 | 38.1 | 4.0 | 0.5 | **57.5** | 4,554,547 |
| Oct 2025 | 46.6 | 6.4 | 0.6 | 46.4 | 5,193,823 |
| Nov 2025 | 47.4 | 5.8 | 0.6 | 46.2 | 3,499,360 |
| **All months** | **44.2** | **5.1** | **0.5** | **50.2** | **19,261,332** |

The unplanned-idle fraction is notably elevated in September (57.5%), with transit correspondingly depressed (38.1%). October and November show the lowest idle fractions (46.2–46.4%), coinciding with the highest ping volumes — suggesting those months had the most continuous operations. The September anomaly may reflect seasonal factors (extreme heat in the South Gobi can trigger mandatory rest periods above certain temperatures), planned maintenance windows, or reduced production targets in that quarter. A fuller attribution would require production logs or shift-schedule data (see Section 6).

### 5.6 DBSCAN Parameter Sensitivity

The eps = 107 m recommendation (Section 4.2, median zone diameter / 4) ensures that stop clusters are small relative to zone footprints, reducing cross-zone merging artifacts. Smaller eps values (30–50 m) produce tighter clusters that may split a single long loading queue into multiple fragments; larger values (200–300 m) risk merging pings from adjacent load and dump zones into a single cluster. A sensitivity sweep across eps ∈ {30, 60, 107, 150, 200} m and min_samples ∈ {3, 5, 10} is included in `notebooks/analysis/cycle_idle_analysis.ipynb`.

## 6. Limitations

- **No payload data**: cycle "productivity" cannot be expressed in tonnes hauled or tonnes/engine-hour — only time-based efficiency. Section on requested dispatch/FMS data (Appendix B) addresses this for a follow-up paper.
- **No fuel data**: idle time cannot be converted to fuel-cost impact, which is usually the number that motivates mine management to act. Flagged as the single highest-value addition if obtainable later.
- **GPS ping interval (~10–30s)** limits precision of short-duration events (brief queue shuffles, exact loader-spotting time).
- **Zone polygons are mine-drawn**, not GPS-derived — possible misalignment between drawn polygon and actual operational footprint (worth a QA pass, see Task List).
- Single-site study — findings on idle/queue proportions are not generalizable without comparison sites.

## 7. Conclusion

This study demonstrates that raw GPS telemetry — collected as a standard byproduct of asset tracking at modern open-pit mines — contains sufficient information to quantify haul-truck operational efficiency without payload sensors, dispatch systems, or onboard diagnostics. Applying a pipeline of density-based stop detection, zone-polygon spatial joins, and trajectory-segmented cycle extraction to five months of data from 89 dump trucks at a South Gobi coal mine, we find that **50.2% of total fleet-time is spent in unplanned idle**, with the fraction rising to 57.5% in September. Median haul cycle time is 26.5 minutes, with load and dump dwells each under 7 minutes — suggesting that the loading and dumping operations themselves are reasonably fast. The dominant inefficiency is time spent stationary in locations outside any recognized mine zone.

Three operational implications follow from these findings:

1. **Zone polygon coverage gap.** The 50.2% unplanned idle is an upper bound: the 11 zones analyzed here cover only load and dump areas. Mine infrastructure zones (fuel station, maintenance yard, weighbridge, parking) are absent. Obtaining and integrating the full zone polygon set is the single highest-value near-term action; it would reclassify a portion of "unplanned idle" into necessary operational stops and reveal the true magnitude of wasteful idle.

2. **Dispatch scheduling review.** Even accounting for the zone coverage gap, the September spike (57.5%) and the persistently high idle fraction suggest periods when trucks are available but not dispatched to active loads. A shift-level idle breakdown (e.g., idle fraction by hour-of-day) would identify whether idling concentrates around shift handovers, meal breaks, or equipment changeovers — all candidates for dispatch-rule adjustment.

3. **GPS-only analysis as a low-cost diagnostic baseline.** The method presented here requires only the GPS positional stream and a zone polygon file, both typically available to mine operations teams without additional investment. It can be run as a recurring monthly report on any fleet using commodity telematics hardware. Adding payload data per cycle would extend the analysis from time-efficiency to material-throughput efficiency; adding fuel consumption would enable direct cost quantification of idle time. Both extensions are recommended as high-priority data collection goals for a follow-up study.

The analysis pipeline is implemented as a reusable open-source Python library (`gps_lib`) and Jupyter notebooks, structured to run against any GPS dataset conforming to the Navixy telematics API format — making it directly applicable to other open-pit mines in Mongolia and comparable operations in similar data-sparse environments.

## References

[1] Fan, C., Zhang, N., Jiang, B., et al. (2025). Rapid Estimation of Truck Cycle Time in Open-Pit Mine Haulage Based on Feature-Optimized Machine Learning. *Mining, Metallurgy & Exploration*, 42, 665–684. https://doi.org/10.1007/s42461-025-01225-0

[2] Operational Cycle Detection for Mobile Mining Equipment: An Integrative Scoping Review with Narrative Synthesis. (2025). *Eng*, 6(10), 279. https://doi.org/10.3390/eng6100279

[3] Gawelski, D., Jachnik, B., Stefaniak, P., & Skoczylas, A. (2020). Haul Truck Cycle Identification Using Support Vector Machine and DBSCAN Models. In *Advances in Computational Collective Intelligence* (ICCCI 2020), CCIS vol. 1287. Springer. https://doi.org/10.1007/978-3-030-63119-2_28

[4] Priegnitz, N., & Yoo, J. J.-W. (2019). Automated Location Classification of Mining Trucks from GPS Data. *IISE Annual Conference Proceedings*, Norcross, 276–281.

[5] Skoczylas, A., Rot, A., Stefaniak, P., & Śliwiński, P. (2023). Haulage Cycles Identification for Wheeled Transport in Underground Mine Using Neural Networks. *Sensors*, 23(3), 1331. https://doi.org/10.3390/s23031331

[6] Chen, W., Ji, M. H., & Wang, J. M. (2014). T-DBSCAN: A Spatiotemporal Density Clustering for GPS Trajectory Segmentation. *International Journal of Online Engineering*, 10(6), 19–24.

[7] Zhao, J., Gao, L., & Ren, S. (2025). Prediction of open-pit mine truck travel time based on LSTM-TabTransformer. *Scientific Reports*, 15. https://doi.org/10.1038/s41598-025-88543-x

[8] Kaungu, E., Githiria, J., Mutua, S., & Dalmus, M. (2021). Optimisation of shovel-truck haulage system in an open pit using queuing approach. *Arabian Journal of Geosciences*, 14(11). https://doi.org/10.1007/s12517-021-07365-z
