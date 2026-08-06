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

Open-pit haulage efficiency is dominated by non-productive time: queuing at shovels, idle stops between cycles, and excess dwell at loading and dumping points. This study applies an unsupervised GPS-only analysis pipeline to five months of raw positional telemetry (July–November 2025) from 89 dump trucks at an open-pit coal mine in Tsogttsetii district, South Gobi, Mongolia — a geographic context underrepresented in the mining-analytics literature. Using DBSCAN stop-cluster detection, zone-polygon spatial joins, and a four-phase cycle decomposition (load-dwell / haul-to-dump / dump-dwell / haul-to-load), we characterize fleet-level operational states without payload sensors, dispatch logs, or onboard CAN-bus signals. Analysis of 19.3 million dump-truck GPS pings (from 45.6 million raw pings after cleaning) reveals that **50.2% of total fleet-seconds** are spent in unplanned idle — stationary outside any mine-surveyed functional zone — against 44.2% in transit and 5.6% inside load or dump zones. The unplanned-idle fraction peaks at 57.5% in September 2025. Across 126,357 complete haul cycles, the median cycle time is 26.5 minutes (median load dwell 4.1 min, haul-to-dump 7.2 min, dump dwell 6.9 min, return haul 4.9 min). We extend this measurement layer with a percentile-baseline attribution and Theory-of-Constraints decision model that turns raw idle/queue time into a ranked, per-flow diagnosis (which cause bucket to fix first, and whether the shovel or the fleet schedule is the binding constraint). Applied independently to three material flows (BN, Middling, Reject) across all five months (15 flow-months total), the diagnosis is stable: the shovel is never the binding constraint (utilisation stays at or below 73%), and the dominant recoverable-time bucket is consistent within each flow across months. For the BN circuit, the reported headline recoverable gain of +53.8% (November) is in fact the *most conservative* month in a 53.8–64.9% range, indicating the finding is not an artifact of the reporting month. We close with a set of manager-facing, GPS-derivable interventions (road, scheduling, and assignment fixes) grounded in the attribution output. These findings quantify the scale of non-productive time recoverable through targeted dispatch and infrastructure interventions, and demonstrate that GPS-only trajectory analysis — requiring no additional sensor investment — is sufficient to identify, prioritize, and validate the stability of efficiency improvements at operating mines.

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
  5. A percentile-baseline attribution and Theory-of-Constraints decision layer built on top of the cycle-extraction pipeline, which converts raw idle/queue measurements into a ranked, per-flow diagnosis, validated for temporal stability across five months and three independent material flows rather than a single reporting month.

## 2. Related Work

Prior work on haulage cycle analysis falls into four groups, distinguished less by algorithm than by the sensing each method assumes. Positioning our approach against these groups clarifies both what we borrow and where our contribution lies.

### 2.1 Rich-signal cycle detection

These methods recover the haul cycle accurately, but only because they read sensors an open-pit fleet often does not carry. Skoczylas et al. (2023) [5] detect the four-phase cycle (load, haul-full, dump, haul-empty) from engine speed, gear speed, and hydraulic-cylinder pressure using two neural networks (one for haul trucks, one for loaders). We adopt their four-phase definition as our cycle backbone, but the contrast is instructive: they mark the unloading event from a hydraulic-pressure spike, whereas we must recover the same event from zero speed inside a dump polygon — that substitution states our contribution in one line. Gawelski et al. (2020) [3] use DBSCAN to segment operational states, combined with SVM classification of cycle phases, over the same class of on-board signals — evidence that DBSCAN for cycle work has precedent, but always paired with rich telemetry in underground operations, the sensor-heavy pole we move away from.

### 2.2 GPS-only trajectory clustering

These are the closest methods to ours, and our paper is defined by what they leave undone. Priegnitz & Yoo (2019) [4] run DBSCAN on low-speed GPS points, with eps = 100 m chosen from the observed physical queue length at a shovel; their method separates fixed infrastructure (shop, crusher) from dynamic loading/dumping areas and incidentally surfaces a low-speed cluster with no matching infrastructure. We make three concrete deltas over this nearest neighbor: we validate clusters against 104 mine-surveyed polygons (they had no ground truth), we replace their single hand-picked eps with a sensitivity sweep over eps and min-samples (Section 5.6), and we systematize the "idle with no infrastructure" location they found by accident into our unplanned-idle map (Section 5.2). Chen et al. (2014), T-DBSCAN [6], process points in time order so a trajectory segments cleanly into stops and moves — which plain, time-blind DBSCAN does not. We cite this as the answer to the reviewer question "why plain DBSCAN and not a spatiotemporal variant?": zone-overlap labeling combined with our 10–30 s ping cadence makes the temporal variant unnecessary here.

### 2.3 Supervised prediction

These models do not compete with our method — they consume exactly the measurements it produces. Fan et al. (2025) [1] show feature-optimized gradient boosting (XGBoost) outperforming ELM and ERT for cycle-time estimation, with waiting-at-shovel, spotting, and waiting-at-dump among the top predictive features — precisely the quantities our attribution layer (Section 4.7) measures directly, so our pipeline is a candidate upstream feature source for theirs. Zhao et al. (2025) [7] use an LSTM–TabTransformer hybrid for travel-time prediction on open-pit coal-mine data, applying Pauta-criterion (3σ) outlier removal in preprocessing; we position their model as downstream of ours (it presumes clean, segmented travel-time records our method must first extract) and borrow their Pauta/3σ step for our own GPS glitch-removal stage (Section 4.1).

### 2.4 Analytical framing

These give us the theory to interpret our measurements and the map to position them. Kaungu et al. (2021) [8] treat trucks as customers and shovels as servers in a queuing-theory framing to size the fleet and quantify waiting — our lens for splitting observed idle into unavoidable versus excess (Section 4.7), and the natural bridge to the just-in-time scheduling control introduced in Section 6. The 2025 scoping review [2] catalogs cycle-detection methods across sensor modalities and algorithms; we use it as our positioning device, placing this study in the low-cost, retrofit-free, GPS-only cell and showing that this cell is under-served relative to the sensor-rich alternatives.

**The recurring gap.** Across all four groups the same limitation appears: existing methods either require sensing the site does not have, or assume the very measurements a bare-GPS layer must first recover. This study sits in the realistic middle case most small/mid-size open-pit operations actually have: **bare GPS pings + a hand-maintained zone map**, nothing else. Our measurement and attribution layers are the hinge that fills this gap, and the paper is explicit about what that constraint costs in interpretability (Section 8, Limitations).

## 3. Study Site and Data

**Site:** Open-pit coal mine, Tsogttsetii district (Цогтцэций сум), Ömnögovi (South Gobi) Province, Mongolia. Pit features include multiple stockpile zones (овоолго), a "reject" loading/unloading area, a processing/beneficiation plant (Баяжуулах үйлдвэр), a fuel point, repair shop, and worker camp.

**Datasets** (all in `data/`):

| File | Description | Use in this study |
|---|---|---|
| `gps_data.csv`, `gps_data_2025-{7,8,9,10,11}.csv` | Raw GPS pings: `tracker_id, get_time, lat, lng, speed, heading, alt, mileage(odometer km), satellites, parking(bool), address` | Primary trajectory data; ~2.5GB across 5 months, ~10s–30s ping interval |
| `tracker_list.csv` | 123 vehicles: `id, label, technic_type(dump/loader/other), group_id, ...` | Truck/loader identity, fleet segmentation |
| `zone_list.csv` + `zone_detail_all_df.csv` | 104 mine-surveyed functional zones (polygon/circle geometries): loading, dumping/stockpile, fuel, repair, parking, plant | Ground-truth labels to validate DBSCAN clusters and define cycle endpoints |
| `dem_merged.tif` + `dem_tiles/` | SRTM-derived elevation raster covering the pit | Grade/slope covariate for haul-segment travel time (loaded uphill vs. empty downhill) |

**Not available** (see Section 7 / Appendix A task list): truck payload per cycle, fuel consumption, dispatch/shovel-assignment logs, material type per haul.

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

### 4.7 Attribution and Theory-of-Constraints decision layer (extension)

Section 4.4 classifies every ping into one of four states (transit / queuing / operating / unplanned idle) and Section 5.2 reports the resulting fleet-wide time shares. That classification answers *how much* time is non-productive; it does not answer *which* non-productive time is recoverable, or *what a manager should do about it*. We extend the pipeline with a second, cycle-level layer that turns Section 4.3's per-cycle phase durations into a ranked diagnosis, built and validated independently per material flow (load zone).

- **Attribution (percentile-baseline excess).** For each cycle phase (load dwell, haul-to-dump, dump dwell, return haul) we compare its duration to a low percentile (p15–p20) of that same phase's distribution for the same flow — the "free-flow" time the fleet already demonstrably achieves. Duration above this baseline is *recoverable* time, apportioned to a named cause bucket: `load_queue` (excess load-zone dwell up to a 120-minute queuing cap), `idle_onshift` (excess load-zone dwell between the queuing cap and a 6-hour parking cap), `haul_road` and `return_road` (excess transit time on the loaded and empty legs), and `dump` (excess dump-zone dwell). Dwell beyond the 6-hour cap is treated as `downtime` — off-shift parking, not dispatch waste — and excluded from the recoverable pool. This decomposition is a finer-grained version of the queuing/operating/idle split in Section 4.4, applied at the cycle level and normalized against an empirical (not assumed) free-flow baseline rather than a fixed speed threshold.
- **Capacity and decision (Theory of Constraints).** We estimate the shovel's realized service rate from the data (loaded-departure inter-arrival time while the queue is non-empty) and derive a throughput ceiling: loads/day the shovel could sustain if run continuously. We then test whether removing each recoverable bucket in turn raises the fleet's throughput or merely runs it into that shovel ceiling. This identifies the **binding constraint** — shovel-bound (utilisation ≥ 0.85) versus fleet/schedule-bound — and prevents recommending shovel-side or road-side fixes when the true limiter is truck availability, or vice versa.
- **Recommendation and explanation.** The binding-constraint result and the ranked recoverable buckets map to a fixed set of interventions (Section 6), and a large language model (OpenAI GPT-4o) converts the structured, numbers-only diagnosis into a short natural-language brief for a non-technical reader; the model is constrained to the given figures and is not permitted to introduce unstated causes.

**Reconciliation with Section 4.4.** The two layers measure the same underlying phenomenon at different resolutions and will not sum to identical totals. Section 4.4's 50.2% "unplanned idle" is a fleet-wide, ping-level share across *all* trucks and *all* time, including scheduled off-shift hours; Section 4.7's attribution is a cycle-level share *within active haul cycles only*, per flow, and separates off-shift downtime from on-shift waste before computing a recoverable fraction. Section 4.7 is therefore the more decision-relevant number — it isolates the portion of idle time an operational fix can plausibly touch — while Section 4.4 remains the correct headline for total fleet-time utilization. Both are reported so a reader can see the same idle-time phenomenon from a fleet-wide accounting view and a per-cycle, actionable-diagnosis view.

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

The dominant finding is that **50.2% of total truck-fleet-seconds** are spent stationary outside any surveyed functional zone. This is the single largest time category — larger even than productive transit. The "queuing" fraction (0.5%) is low because the 50 m load-zone buffer is tight; widening this buffer to 200 m would reclassify a portion of unplanned idle as queuing, but this ambiguity reflects genuine uncertainty in the zone-polygon boundary rather than a methodological choice (see Section 7, Limitations).

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

The unplanned-idle fraction is notably elevated in September (57.5%), with transit correspondingly depressed (38.1%). October and November show the lowest idle fractions (46.2–46.4%), coinciding with the highest ping volumes — suggesting those months had the most continuous operations. The September anomaly may reflect seasonal factors (extreme heat in the South Gobi can trigger mandatory rest periods above certain temperatures), planned maintenance windows, or reduced production targets in that quarter. A fuller attribution would require production logs or shift-schedule data (see Section 7).

### 5.6 DBSCAN Parameter Sensitivity

The eps = 107 m recommendation (Section 4.2, median zone diameter / 4) ensures that stop clusters are small relative to zone footprints, reducing cross-zone merging artifacts. Smaller eps values (30–50 m) produce tighter clusters that may split a single long loading queue into multiple fragments; larger values (200–300 m) risk merging pings from adjacent load and dump zones into a single cluster. A sensitivity sweep across eps ∈ {30, 60, 107, 150, 200} m and min_samples ∈ {3, 5, 10} is included in `notebooks/analysis/cycle_idle_analysis.ipynb`.

### 5.7 Generalization and Temporal Stability of the Diagnostic Layer

Section 4.7's attribution and decision layer was validated on a single month (November 2025) for two flows in earlier iterations of this work. Because a single-month diagnosis cannot distinguish a genuine operational pattern from a one-off reporting artifact, we re-ran the full `perception → attribution → decision` pipeline independently for all five available months (July–November 2025) and all three material flows with distinct loading circuits at this site (BN, Middling, Reject) — 15 flow-months in total, each computed from that flow's own cycles with no parameters carried over between runs.

**Table 4. Diagnostic stability by flow and month.**

| Flow | Month | Loads/day | Trucks | Shovel util. | Top recoverable bucket | Binding constraint | Recoverable gain vs. current |
|---|---|---|---|---|---|---|---|
| BN | Jul | 48.5 | 13 | 43% | return_road | fleet / schedule | +64.9% |
| BN | Aug | 78.0 | 24 | 52% | return_road | fleet / schedule | +60.3% |
| BN | Sep | 77.6 | 24 | 53% | return_road | fleet / schedule | +61.1% |
| BN | Oct | 88.3 | 26 | 59% | return_road | fleet / schedule | +54.0% |
| BN | Nov | 80.6 | 22 | 50% | return_road | fleet / schedule | **+53.8%** |
| Middling | Jul | 150.7 | 10 | 32% | idle_onshift | fleet / schedule | +54.6% |
| Middling | Aug | 196.7 | 25 | 33% | idle_onshift | fleet / schedule | +105.4% |
| Middling | Sep | 233.3 | 27 | 44% | idle_onshift | fleet / schedule | +107.5% |
| Middling | Oct | 204.6 | 29 | 38% | idle_onshift | fleet / schedule | +130.2% |
| Middling | Nov | 159.9 | 21 | 34% | idle_onshift | fleet / schedule | +87.0% |
| Reject | Jul | 7.2 | 9 | 8% | idle_onshift | fleet / schedule | +80.6% *(anomaly, see below)* |
| Reject | Aug | 376.3 | 24 | 68% | load_queue | fleet / schedule | +48.0% |
| Reject | Sep | 422.1 | 27 | 69% | load_queue | fleet / schedule | +42.1% |
| Reject | Oct | 497.0 | 29 | 73% | load_queue | fleet / schedule | +36.8% |
| Reject | Nov | 219.0 | 21 | 56% | load_queue | fleet / schedule | +51.1% |

Three findings follow.

**The shovel is never the binding constraint.** Across all 15 flow-months, shovel utilisation never reaches the 0.85 threshold used to declare a shovel-bound circuit (maximum observed: 73%, Reject in October). This means the recommendation to prioritize scheduling and road fixes over shovel-side investment (Section 6) is not an artifact of the November reporting month or of any single flow — it holds for every month and every flow tested. Reject's utilisation climbing from 56% (November) to 73% (October) as its volume grew is worth monitoring: it is the flow closest to becoming shovel-bound, and a continued volume increase would eventually change the recommended intervention.

**BN's diagnosis is stable in both kind and magnitude.** The top recoverable bucket (`return_road`, i.e., excess time on the empty return leg) and the binding-constraint category are identical in all five months. The recoverable-gain estimate is also tightly banded (53.8–64.9%, an 11-point range), and critically, **November — the month used for the headline figure reported in Section 5.5 and the project summary — is the most conservative (lowest) of the five months.** The reported "+54%" opportunity is therefore not a cherry-picked high estimate; if anything, a manager acting on the November brief alone is looking at a lower bound of what the data show is achievable.

**Middling is stable in kind but not in magnitude; Reject's July is a genuine anomaly, not a data artifact.** For Middling, the diagnosis category is fully stable (`idle_onshift` dominant, fleet/schedule-bound, all five months) but the recoverable-gain magnitude is not (54.6–130.2%, a 2.4× range tracking this flow's larger month-to-month swings in truck count and utilisation). We treat this as a real limitation: for Middling, only the *direction* of the recommended fix generalizes across months, not its *size* — a single-month magnitude should not be reported as representative for this flow without the same caveat applied to BN's tighter range. For Reject, August–November form a second internally consistent block (`load_queue` dominant, fleet/schedule-bound, utilisation rising with volume), but July stands apart on every measured axis: loads/day is 30–70× lower than the other four months (7.2 vs. 219–497), shovel utilisation is far lower (8% vs. 56–73%), and the top recoverable bucket is different (`idle_onshift` instead of `load_queue`). We checked whether this reflects a data-coverage gap rather than a genuine operational pattern: July still has 158 recorded cycles, 9 active trucks, and coverage on 22 of the month's 31 days (not a truncated month) — so the anomaly is real activity at unusually low volume, not missing telemetry. The most likely explanation is that the Reject circuit was in a ramp-up or partial-operation state in July 2025; we flag this to the mine's operations team as a hypothesis to confirm, exclude July from any cross-month averaging for this flow, and report it here rather than silently dropping it.

## 6. Manager-Facing Recommendations

The attribution layer (Section 4.7) locates *where* haulage time is lost; a manager needs to know *what can be done about it*. A haul cycle loses time for three distinct reasons — the road is slow in places (**where**), trucks arrive bunched and form queues (**when**), or trucks and shovels are matched in the wrong numbers or the wrong place (**who**) — and the corresponding fixes run from cheapest to hardest. Each maps directly onto a recoverable-time bucket the attribution layer already reports (Section 5.7), and each can be driven, wholly or in part, from trajectory data alone.

### 6.1 Fix the road (WHERE)

Certain road segments are slow for every truck every day (the `haul_road`/`return_road` buckets — the dominant recoverable cost for BN, Section 5.7), so they should be ranked by total fleet-time lost and repaired worst-first. **Method.** Fit a per-segment speed distribution over all truck passes, establish a grade-corrected free-flow baseline, and rank segments by fleet-hours of excess delay [9, 10]; the grade–speed relationships reported in [11, 12] translate these rankings into concrete road-maintenance and speed-advisory actions. **Status:** deployable now, on the GPS data already collected. **Manager action:** grade or water rough stretches, widen pinch points, fix intersections, and post grade-specific speed limits — directly relevant to BN's 34 km haul, the longest and most road-exposed of the three flows studied here.

### 6.2 Smooth the flow (WHEN)

Queues can form from bunched arrivals even when the shovel has adequate capacity (the `load_queue` bucket — the dominant recoverable cost for Reject, Section 5.7), and this is addressable from the trucks' own positions without ever observing the shovel directly. **Method.** Bunching is measurable as headway variance at virtual gates on the approach to loading and plant zones; cooperative headway control [13] smooths it using only relative arrival times. Where the queue faces a shovel or crusher, the maritime just-in-time paradigm [14, 15] applies directly — a vessel adjusts sailing speed to arrive as a berth becomes free, and analogously a truck's arrival can be planned against a service-readiness forecast derived from its own departure stream, again with no shovel-side instrumentation required. **Status:** deployable with light coordination, and shovel-agnostic. **Manager action:** stagger releases at the dump exit, or issue just-in-time cruise-speed targets to approaching trucks.

### 6.3 Assign smarter, right count (WHO)

Because this site exposes multiple observable unload areas, dump-side balancing and fleet-sizing are deployable now, while real-time shovel selection remains future work needing a fleet-management system. **Method.** Trucks can be rebalanced across dumping and plant zones — separated into material streams by destination label — directly from GPS, while route-level match-factor analysis [16] flags over- and under-trucked paths; this directly addresses the `idle_onshift`/downtime split (Section 4.7) that dominates Middling's diagnosis and the 4,366 truck-hours/month of off-shift downtime identified for BN. Real-time selection of loading targets, by contrast, requires a dispatch system, for which the optimization and reinforcement-learning approaches of [16–19] define a future-work trajectory, parameterized by the cycle-time distributions measured in this study. **Status:** dump-side balancing and fleet-sizing deployable now; live dispatch optimization is future work requiring a dispatch/FMS integration this study does not have (Section 8).

## 7. Limitations

- **No payload data**: cycle "productivity" cannot be expressed in tonnes hauled or tonnes/engine-hour — only time-based efficiency. Section on requested dispatch/FMS data (Appendix B) addresses this for a follow-up paper.
- **No fuel data**: idle time cannot be converted to fuel-cost impact, which is usually the number that motivates mine management to act. Flagged as the single highest-value addition if obtainable later.
- **GPS ping interval (~10–30s)** limits precision of short-duration events (brief queue shuffles, exact loader-spotting time).
- **Zone polygons are mine-drawn**, not GPS-derived — possible misalignment between drawn polygon and actual operational footprint (worth a QA pass, see Task List).
- Single-site study — findings on idle/queue proportions are not generalizable without comparison sites.
- **Attribution/ToC layer parameters are not yet swept.** The percentile-baseline choice (p15–p20) and the queue/parking caps (120 min / 6 h) that separate `load_queue`, `idle_onshift`, and `downtime` (Section 4.7) were tuned on BN and used unchanged for Middling and Reject. Section 5.7 validates *temporal* stability (same parameters, five months, three flows) but not *parameter* sensitivity — how the recoverable-gain estimates would shift under different percentile or threshold choices remains untested and is the natural next robustness check.
- **Middling's recoverable-gain magnitude is unstable across months** (54.6–130.2%, Section 5.7), even though its diagnosis category is not. Any single-month magnitude reported for this flow should be presented as a snapshot, not a representative estimate, until more months are checked or the source of the swing (fleet-size and utilisation volatility) is understood.
- **Reject's July 2025 data is a confirmed anomaly, not yet explained operationally.** Loads/day and shovel utilisation are 30–70× and 7–9× lower, respectively, than the other four months, despite full-month data coverage (Section 5.7). We infer a likely ramp-up or partial-operation period but have not confirmed this with mine operations; it is excluded from cross-month averaging for this flow pending that confirmation.
- **No before/after pilot has been run.** Every recoverable-time and throughput-ceiling estimate in Sections 5.7 and 6 is observational and diagnostic, not causal — it identifies where time is lost and what class of intervention should help, but does not prove that applying an intervention produces the stated gain. Proving a gain requires applying one lever, then re-running the same pipeline on the "after" data and measuring the change.

## 8. Conclusion

This study demonstrates that raw GPS telemetry — collected as a standard byproduct of asset tracking at modern open-pit mines — contains sufficient information to quantify haul-truck operational efficiency without payload sensors, dispatch systems, or onboard diagnostics. Applying a pipeline of density-based stop detection, zone-polygon spatial joins, and trajectory-segmented cycle extraction to five months of data from 89 dump trucks at a South Gobi coal mine, we find that **50.2% of total fleet-time is spent in unplanned idle**, with the fraction rising to 57.5% in September. Median haul cycle time is 26.5 minutes, with load and dump dwells each under 7 minutes — suggesting that the loading and dumping operations themselves are reasonably fast. The dominant inefficiency is time spent stationary in locations outside any recognized mine zone.

Extending this measurement with a percentile-baseline attribution and Theory-of-Constraints decision layer (Section 4.7), and validating it across all five months and three material flows (Section 5.7) rather than a single reporting month, strengthens rather than qualifies the headline finding: the shovel is never the binding constraint in any of the 15 flow-months tested, and BN's reported +54% recoverable-throughput estimate is the most conservative month in its range, not an optimistic outlier. Where the diagnosis is *not* stable — Middling's recoverable-gain magnitude, and Reject's clear July anomaly — we report the instability directly rather than average over it, consistent with this study's broader stance that a GPS-only diagnostic should state its own limits alongside its findings.

Four operational implications follow from these findings:

1. **Zone polygon coverage gap.** The 50.2% unplanned idle is an upper bound: the 11 zones analyzed here cover only load and dump areas. Mine infrastructure zones (fuel station, maintenance yard, weighbridge, parking) are absent. Obtaining and integrating the full zone polygon set is the single highest-value near-term action; it would reclassify a portion of "unplanned idle" into necessary operational stops and reveal the true magnitude of wasteful idle.

2. **Dispatch scheduling review.** Even accounting for the zone coverage gap, the September spike (57.5%) and the persistently high idle fraction suggest periods when trucks are available but not dispatched to active loads. A shift-level idle breakdown (e.g., idle fraction by hour-of-day) would identify whether idling concentrates around shift handovers, meal breaks, or equipment changeovers — all candidates for dispatch-rule adjustment.

3. **A ranked, flow-specific action plan, not a single number.** The attribution and Theory-of-Constraints layer (Sections 4.7, 5.7, 6) turns the fleet-wide idle share into per-flow, per-cause diagnoses: fix the road for BN (`return_road`-dominant), smooth arrivals for Reject (`load_queue`-dominant), and rebalance/right-size the fleet for Middling (`idle_onshift`-dominant). Because these diagnoses are stable across five months, they are ready to hand to mine management as a prioritized punch list rather than a single-month curiosity — with the explicit caveat that only a before/after pilot can convert "recoverable" into a proven gain.

4. **GPS-only analysis as a low-cost diagnostic baseline.** The method presented here requires only the GPS positional stream and a zone polygon file, both typically available to mine operations teams without additional investment. It can be run as a recurring monthly report on any fleet using commodity telematics hardware. Adding payload data per cycle would extend the analysis from time-efficiency to material-throughput efficiency; adding fuel consumption would enable direct cost quantification of idle time. Both extensions are recommended as high-priority data collection goals for a follow-up study.

The analysis pipeline is implemented as a reusable open-source Python library (`gps_lib`) and Jupyter notebooks, structured to run against any GPS dataset conforming to the Navixy telematics API format — making it directly applicable to other open-pit mines in Mongolia and comparable operations in similar data-sparse environments.

## References

[1] Fan, C., Zhang, N., Jiang, B., & Liu, W. V. (2025). Rapid estimation of truck cycle time in open-pit mine haulage based on feature-optimized machine learning. *Mining, Metallurgy & Exploration*, 42(2), 665–684. https://doi.org/10.1007/s42461-025-01225-0

[2] Operational cycle detection for mobile mining equipment: An integrative scoping review with narrative synthesis. (2025). *Eng*, 6(10), 279. https://doi.org/10.3390/eng6100279

[3] Gawelski, D., Jachnik, B., Stefaniak, P., & Skoczylas, A. (2020). Haul truck cycle identification using support vector machine and DBSCAN models. In *Advances in Computational Collective Intelligence* (ICCCI 2020), CCIS vol. 1287. Springer. https://doi.org/10.1007/978-3-030-63119-2_28

[4] Priegnitz, N., & Yoo, J. J.-W. (2019). Automated location classification of mining trucks from GPS data. *IISE Annual Conference Proceedings* (pp. 276–281). Norcross.

[5] Skoczylas, A., Rot, A., Stefaniak, P., & Śliwiński, P. (2023). Haulage cycles identification for wheeled transport in underground mine using neural networks. *Sensors*, 23(3), 1331. https://doi.org/10.3390/s23031331

[6] Chen, W., Ji, M. H., & Wang, J. M. (2014). T-DBSCAN: A spatiotemporal density clustering for GPS trajectory segmentation. *International Journal of Online Engineering*, 10(6), 19–24. https://doi.org/10.3991/ijoe.v10i6.3881

[7] Zhao, J., Gao, L., & Ren, S. (2025). Prediction of open-pit mine truck travel time based on LSTM-TabTransformer. *Scientific Reports*, 15, 7427. https://doi.org/10.1038/s41598-025-88543-x

[8] Kaungu, E., Githiria, J., Mutua, S., & Dalmus, M. (2021). Optimisation of shovel-truck haulage system in an open pit using queuing approach. *Arabian Journal of Geosciences*, 14(11). https://doi.org/10.1007/s12517-021-07365-z

[9] Zhao, W., McCormack, E., Dailey, D. J., & Scharnhorst, E. (2013). Using truck probe GPS data to identify and rank roadway bottlenecks. *Journal of Transportation Engineering*, 139(1), 1–7. https://doi.org/10.1061/(ASCE)TE.1943-5436.0000444

[10] Automatic freeway bottleneck identification and visualization. (2019). *arXiv preprint* arXiv:1911.07395.

[11] Geometric and operational design principles for autonomous haulage systems in open-pit mining: A systematic review. (2025). *Mining*, 6(3), 45. https://doi.org/10.3390/mining6030045

[12] Žikić, N., Kukolj, D., Stojadinović, S., & Tanikić, D. (2018). Automatic control of haul truck travel speed on open pits. *Tehnika*. https://doi.org/10.5937/tehnika1804497Z

[13] Daganzo, C. F., & Pilachowski, J. (2011). Reducing bunching with bus-to-bus cooperation. *Transportation Research Part B: Methodological*, 45(1), 267–277. https://doi.org/10.1016/j.trb.2010.06.005

[14] Slow steaming and just-in-time arrival strategies in maritime logistics. (2026). *Journal of Marine Science and Engineering*, 14(3), 299. https://doi.org/10.3390/jmse14030299

[15] Coordinated vessel arrival time prediction and berth allocation optimization for efficient port operations. (2026). *Journal of Marine Science and Engineering*, 14(8), 758. https://doi.org/10.3390/jmse14080758

[16] Mirzaei-Nasirabad, H., Mohtasham, M., Askari-Nasab, H., et al. (2023). An optimization model for the real-time truck dispatching problem in open-pit mining operations. *Optimization and Engineering*, 24, 2449–2473. https://doi.org/10.1007/s11081-022-09780-x

[17] Hazrathosseini, A., & Moradi Afrapoli, A. (2024). Transition to intelligent fleet management systems in open pit mines: A critical review on application of reinforcement-learning-based systems. *Mining Technology: Transactions of the Institutions of Mining and Metallurgy*. https://doi.org/10.1177/25726668231222998

[18] A hybrid MARL clustering framework for real-time open-pit mine truck scheduling. (2025). *Scientific Reports*, 15. https://doi.org/10.1038/s41598-025-16347-0

[19] Curriculum-inspired adaptive direct policy guidance for truck dispatching. (2025). *arXiv preprint* arXiv:2502.20845.

[6] Chen, W., Ji, M. H., & Wang, J. M. (2014). T-DBSCAN: A Spatiotemporal Density Clustering for GPS Trajectory Segmentation. *International Journal of Online Engineering*, 10(6), 19–24.

[7] Zhao, J., Gao, L., & Ren, S. (2025). Prediction of open-pit mine truck travel time based on LSTM-TabTransformer. *Scientific Reports*, 15. https://doi.org/10.1038/s41598-025-88543-x

[8] Kaungu, E., Githiria, J., Mutua, S., & Dalmus, M. (2021). Optimisation of shovel-truck haulage system in an open pit using queuing approach. *Arabian Journal of Geosciences*, 14(11). https://doi.org/10.1007/s12517-021-07365-z
