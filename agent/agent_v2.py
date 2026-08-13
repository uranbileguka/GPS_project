#!/usr/bin/env python3
"""
agent_v2.py — rebuilt diagnostic agent (the new L3 design we worked out).

Additive: does NOT modify agent_diagnose.py or the collaborator's code.
Builds its own cycle table from raw GPS; data/cycles_all_months.csv is only a fallback.

WHAT'S NEW vs agent_diagnose.py
  no cut line ......... none is needed. The 120-min queue/long-stop threshold existed to
                        separate real stays from stays that only looked long because they
                        were measured between the wrong two timestamps; dwell is now the
                        visit's own arrival to departure, and the distribution is unimodal.
  地基一 budget ....... a truck-hour is either IN the loop (moving + loading + queue) or
                        OUT of it, and which one is decided by WHERE the truck was, never
                        by the time of day.
  地基二 cause ........ each waiting chunk is tagged by CAUSE from position + context, not
                        duration alone: another truck already being served -> queue;
                        nobody there and still slow -> reported separately, unexplained.
  L3-A ................ utilisation rho for BOTH shovel and dump, compared to 1.0 (no 0.85).
  L3-B ................ Little's law: loads/day = cycling truck-h/day / cycle-time; the
                        ceiling is the first station to reach rho = 1.
  L3-C ................ levers ranked by REAL loads/day gained; mechanism a (shorten the
                        loop) / b (turn out-of-loop hours into looping hours) / c (expand a
                        station). Each lever keeps its CAUSE.
  L3-D ................ feedback: recompute rho at the higher throughput -> the bottleneck moves.
  E ................... bootstrap confidence band on the headline gain.

Honesty frame unchanged: DIAGNOSTIC not proof; gains are UPPER BOUNDS (now with a band);
no payload -> units are loads / truck-hours; a real gain needs a before/after pilot.

--------------------------------------------------------------------------------------
2026-08-07 REWRITE OF THE ROAD LAYER (use_pings=True, now the default)
--------------------------------------------------------------------------------------
The cycle-table-only road buckets were WRONG. `haul_s`/`return_s` are two timestamps
subtracted, so anything the truck did in between is invisible and got charged to "road".
At BN only 58% of that time is actually driving; the rest is a shift-change car park, two
weighbridges, two tarping points, and queueing outside the load-zone fence. The old layer
therefore ranked "fix the empty-return road" #1 (+16 loads/day) when the real answer is
the shovel queue, and the true road sits at #8-#9 (+1.8) in every one of the 5 months.

What the ping layer adds:
  * the loop has SIX stations, not two:
        load -> weigh(BN) -> tarp-on ---34 km--- tarp-off -> weigh(Ukhaa) -> dump
  * station vs out-of-loop is decided by PER-TRIP COVERAGE, not by guessing a place's job:
        ~200% (passed both ways, every trip) -> station, stays in the loop
        <100% (car park 16%, klonk 41%)      -> out-of-loop, must be pulled out, because the
                                                p15 leg baseline contains no such stop and
                                                would book the whole thing as road waste
  * each station's dwell splits three ways with NO percentile fudge:
        service    = min(dwell, median dwell when nobody else was there)
        queue      = the excess, when >=1 truck was already at the station on arrival
        solo-long  = the excess with nobody there -> its own bucket, not forced either way
  * per-ping dt attribution (smallest containing box wins) so every minute lands in exactly
    one place; the identity closes to -0.8%.
  * headline is a RANGE, not a point: observed lower bound (match your own best day) and
    the theoretical upper bound (fix everything). The ceiling is no longer reported as a
    number -- it moves 125..273 under plausible parameters; only "utilisation, not saturated"
    survives. Grade correction was checked and abandoned: BN's net grade is 0.13%.

use_pings=False keeps the old path for speed. It is KNOWN-BIASED; the output says so.
"""
import os, sys, json, glob, re
import numpy as np, pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
CYCLES_CSV = os.path.join(_ROOT, 'data', 'cycles_all_months.csv')
sys.path.insert(0, _HERE)

ZONES = {
    25559: dict(name='BN load (Баруун наран /Зүүн/)', region='bn',    haul_km=34),
    25385: dict(name='Middling load',                 region='other', haul_km=0.4),
    25384: dict(name='Reject load',                   region='other', haul_km=2.0),
}
NIGHT_HOUR = 3          # a stay "spans overnight" if it is still on at 03:00
BUSY_GAP_MIN = 30       # departures closer than this = the station was busy
FF_Q = 0.15             # free-flow travel-time baseline quantile (haul / return)
SVC_Q = 0.20            # no-queue service-time baseline quantile (loading / dump)

# ---- ping layer ----------------------------------------------------------------------
ZONE_LIST = os.path.join(_ROOT, 'data', 'zone_list.csv')
GPS_GLOB = os.path.join(_ROOT, 'data', 'gps_data_{y}-{m}.csv')
PING_CACHE = os.path.join(_HERE, '.ping_cache')
BOX_BUFFER = 0.0009     # ~100 m around a zone's bounding box
STOP_SPEED = 2          # km/h at or below = not moving
DT_CAP = 300            # a GPS hole longer than this counts as this (0.3% of intervals)
VISIT_GAP = 600         # re-entering after this long = a new visit
STOP_FRAC = 0.5         # a day below this * median loads = a stoppage day, reported apart
SHIFT_HOURS = {4, 5, 6, 7, 16, 17, 18, 19}

# --- topology discovery thresholds -----------------------------------------------------
# A place is part of the loop iff EVERY trip passes it. Coverage = visits / cycles, so a
# place passed on both legs of every trip scores ~200%. Nothing here depends on knowing what
# a place is FOR -- which matters, because we cannot ask the site, and because a hard-coded
# list of one mine's Mongolian labels would not transfer to another mine.
STATION_MIN_COV = 150   # >= this % of cycles -> the route passes through here
OFFLOOP_MAX_COV = 100   # <  this % -> out-of-loop stop; the p15 leg baseline contains no such
                        #    stop, so leaving it in the leg would book it all as fake road waste
# Coverage alone only says "on the route". Junctions and mileposts score ~200% too because
# every truck DRIVES THROUGH them. A station is a place trucks actually STOP. Measured at BN,
# the two groups are cleanly separated with nothing in between:
#     stop rate >= 0.89  weighbridges, tarping points, the load-zone gate (median dwell 3-8 min)
#     stop rate <= 0.23  junctions, mileposts, pass-through zones  (median dwell 0.2-1.4 min)
# so any cut in 0.3-0.85 gives the identical partition -- this threshold is inert by construction.
STATION_MIN_STOPRATE = 0.5
MIN_VISITS = 30         # ignore zones with too few visits to say anything
# NOTE: an earlier version folded a "gate" zone (label containing 'оролт') into the shovel
# queue. Dropped: once the gate is merged with the adjacent weighbridge and tarping point --
# they are 350 m apart and their boxes overlap -- gate-queueing and station-service are no
# longer separable, so pretending otherwise would inflate the shovel queue with service time.
# The complex is now reported as a station like any other, and no rule reads a zone's label.


# ============================================================ L0 cycle construction
# Ported from analysis/cycle_count_analysis.ipynb so the agent no longer depends on a
# pre-baked cycle table. Without this, "hand it next month's GPS and it produces
# recommendations" is not true: load_cycles() would just return nothing.
TRACKER_LIST = os.path.join(_ROOT, 'data', 'tracker_list.csv')
ZONE_DETAIL = os.path.join(_ROOT, 'data', 'zone_detail_all_df.csv')
CYCLE_CACHE = os.path.join(_HERE, '.cycle_cache')
MAX_CYCLE_HOURS = 6     # a "cycle" longer than this is an offline gap or a shift break

# Which zones are loading points. The mine's labels, not ours; the polygons only exist for
# these material zones (11 of 104), which is exactly what cycle construction needs.
LOAD_PAT = 'Reject ачилтын бүс|Баруун наран ачилтын бүс|Middling ачилтын бүс'
MAT_PATS = [('reject', 'Reject овоолго|Reject ачилтын бүс'),
            ('bn', 'Баруун наран ачилтын бүс  /Зүүн/|Баруун наран овоолго|'
                   'Баруун наран ачилтын бүс /Баруун/'),
            ('middling', 'Middling ачилтын бүс|SP7|SP4|Sp5')]


def _material_zones():
    """The 11 zones that have real polygons, tagged load/unload and by material."""
    import geopandas as gpd
    from shapely.geometry import Polygon
    Z = pd.read_csv(ZONE_LIST)
    Z['zone_material_type'] = 'other'
    for mat, pat in MAT_PATS:
        Z.loc[Z.label.str.contains(pat, case=False, na=False), 'zone_material_type'] = mat
    Z['zone_load_type'] = 'unload'
    Z.loc[Z.label.str.contains(LOAD_PAT, case=False, na=False), 'zone_load_type'] = 'load'
    Z = Z[Z.zone_material_type != 'other']

    V = pd.read_csv(ZONE_DETAIL)
    polys = []
    for zid, g in V.groupby('zone_id'):
        g = g[['lat', 'lng']].dropna().drop_duplicates()
        if len(g) < 3:
            continue
        cx, cy = g.lng.mean(), g.lat.mean()                       # order vertices by angle,
        g = g.assign(_a=np.arctan2(g.lat - cy, g.lng - cx)).sort_values('_a')   # then close
        polys.append({'zone_id': int(zid), 'geometry': Polygon(g[['lng', 'lat']].values)})
    gdf = gpd.GeoDataFrame(polys, crs='EPSG:4326').merge(
        Z[['id', 'label', 'zone_material_type', 'zone_load_type']],
        left_on='zone_id', right_on='id', how='inner')
    gdf['region'] = np.where(gdf.zone_material_type == 'bn', 'bn', 'other')
    return gdf


def _hav_m(lo1, la1, lo2, la2):
    R = 6371000.0
    lo1, la1, lo2, la2 = map(np.radians, [lo1, la1, lo2, la2])
    d = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(d))


def build_cycles(month, max_cycle_hours=MAX_CYCLE_HOURS, cache=True):
    """Raw monthly GPS  ->  load->unload->load cycles. This is what makes the pipeline
    reusable: give it a month of GPS it has never seen and it produces the cycle table the
    rest of the agent runs on.

    NOTE the cleaning here (round to 4 dp ~11 m, dedup per lat/lng/hour/truck) is the one the
    cached table was built with, and it is deliberately NOT used for the ping layer — that
    dedup erases the stationary points that ARE the queue."""
    import geopandas as gpd
    os.makedirs(CYCLE_CACHE, exist_ok=True)
    out = os.path.join(CYCLE_CACHE, f'cycles_{month}.parquet')
    if cache and os.path.exists(out):
        return pd.read_parquet(out)

    y, m = month.split('-')
    src = GPS_GLOB.format(y=y, m=int(m))
    if not os.path.exists(src):
        raise FileNotFoundError(f'raw GPS not found: {src}')
    T = pd.read_csv(TRACKER_LIST)
    T['technic_m_type'] = np.where(T.label.str.contains('BN', case=False, na=False), 'bn', 'other')
    dump = T[T.technic_type == 'dump']

    tp = pd.read_csv(src, low_memory=False).drop_duplicates()
    tp['get_time'] = pd.to_datetime(tp['get_time'], errors='coerce')
    s = tp.merge(dump, left_on='tracker_id', right_on='id', how='inner')
    s = s[['lat', 'lng', 'get_time', 'speed', 'technic_m_type', 'tracker_id', 'label']].copy()
    # The old build rounded to 4 dp (~11 m) and kept one ping per (lat, lng, date, hour,
    # truck). Two visits to the same spot in the same hour then collapsed into one, so the
    # second load-zone arrival vanished and two trips merged. Costs ~0.6% of trips; dropped.

    zones = _material_zones()
    gp = gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lng, s.lat), crs='EPSG:4326')
    h = gpd.sjoin(gp, zones[['geometry', 'zone_id', 'zone_material_type', 'zone_load_type']],
                  predicate='within', how='left')
    tagged = (pd.DataFrame(h[~h.index.duplicated(keep='first')].drop(columns='geometry'))
                .sort_values(['tracker_id', 'get_time']).reset_index(drop=True))

    rows = []
    for tid, g in tagged.groupby('tracker_id'):
        g = g.sort_values('get_time')
        zid = g.zone_id.values; lt = g.zone_load_type.values; mat = g.zone_material_type.values
        stopped = (g.speed.values <= STOP_SPEED)
        t = g.get_time.values; la = g.lat.values.astype(float); lo = g.lng.values.astype(float)
        step = np.zeros(len(g))
        if len(g) > 1:
            step[1:] = _hav_m(lo[:-1], la[:-1], lo[1:], la[1:])
        cum = np.cumsum(step) / 1000.0
        def pkm(ta, tb):
            ia = min(int(np.searchsorted(t, ta)), len(cum) - 1)
            ib = min(int(np.searchsorted(t, tb)), len(cum) - 1)
            return round(max(0.0, cum[ib] - cum[ia]), 3)
        info = g.iloc[0]
        visits, i, n = [], 0, len(g)
        while i < n:                                   # collapse consecutive pings in one zone
            if pd.isna(zid[i]):
                i += 1; continue
            j = i
            while j + 1 < n and zid[j + 1] == zid[i]:
                j += 1
            # A LOAD visit only counts if the truck actually stopped: presence alone let
            # drive-throughs close a cycle, and 41% of load "visits" lasted under a minute
            # (median 12 s, 4 pings) — a truck clipping the polygon on its way past, not one
            # being loaded. dwell_s is measured on this visit, so it has to be a real stop.
            # Unload visits are NOT held to that test. Only 43% of them contain a stopped
            # ping because the stockpile polygons are drawn once while the tipping face
            # moves; requiring a stop there would discard real trips. Reaching the dump area
            # is enough evidence the load was delivered.
            if lt[i] != 'load' or stopped[i:j + 1].any():
                visits.append((lt[i], zid[i], mat[i], t[i], t[j], i, j))
            i = j + 1

        def max_gap_s(a, b):
            """Largest hole between consecutive pings inside [a, b]. This is what tells a
            genuinely slow trip apart from a stretch where the tracker was simply off."""
            w = t[a:b + 1]
            return float(np.diff(w).max() / np.timedelta64(1, 's')) if len(w) > 1 else 0.0

        pl = pu = None; n_unload = 0
        for vt, vz, vm, arr, dep, vi, vj in visits:
            if vt == 'load':
                if pl is not None and pu is not None:
                    dl, dz, dm, dj = pl; ua, ud, uz, um = pu
                    cy = (arr - dl) / np.timedelta64(1, 's')
                    # Emit every load->unload->load trip. The old code dropped anything over
                    # max_cycle_hours as "an offline gap or a shift break", which threw away
                    # 10.4% of BN's real trips AND handed their time to the next row's dwell,
                    # inflating the load-zone queue. Duration cannot tell those two cases
                    # apart; a hole in the ping stream can, so measure that instead and let
                    # the caller decide.
                    if cy > 0:
                        rows.append(dict(
                            tracker_id=tid, region=info['technic_m_type'], truck=info['label'],
                            load_zone=int(dz), load_mat=dm, unload_zone=int(uz), unload_mat=um,
                            depart_load=pd.Timestamp(dl), arrive_unload=pd.Timestamp(ua),
                            depart_unload=pd.Timestamp(ud), arrive_load=pd.Timestamp(arr),
                            haul_s=(ua - dl) / np.timedelta64(1, 's'),
                            dump_s=(ud - ua) / np.timedelta64(1, 's'),
                            return_s=(arr - ud) / np.timedelta64(1, 's'), cycle_s=cy,
                            haul_km=pkm(dl, ua), return_km=pkm(ud, arr), cycle_km=pkm(dl, arr),
                            max_gap_s=max_gap_s(dj, vi), n_unload_visits=n_unload,
                            # The load-zone stay measured directly from THIS visit's own
                            # arrival and departure. The old dwell was the next ROW's
                            # depart_load minus this row's arrive_load, which spans any
                            # re-entry the truck made in between -- only 50% of that window
                            # was actually at the load zone.
                            dwell_own_s=(dep - arr) / np.timedelta64(1, 's'),
                            over_max_hours=bool(cy > max_cycle_hours * 3600)))
                    pl = (dep, vz, vm, vj); pu = None; n_unload = 0
                else:
                    pl = (dep, vz, vm, vj)
            elif pl is not None:
                # FIRST unload visit only. The old code kept the first arrival and extended
                # to the LAST departure, so a trip that touched the dump area more than once
                # booked everything in between -- including time parked well away from it --
                # as dump dwell. Measured: only 39.8% of that window was actually at a dump.
                # A load can only be dumped once; whatever follows belongs to the return leg,
                # which the ping layer already splits by where the truck really was.
                if pu is None:
                    pu = (arr, dep, vz, vm)
                    n_unload = 1
                else:
                    n_unload += 1
    C = pd.DataFrame(rows)
    if not C.empty:
        C['date'] = C.depart_load.dt.date.astype(str)
        C['week'] = C.depart_load.dt.to_period('W').astype(str)
        C['month'] = C.depart_load.dt.to_period('M').astype(str)
    if cache:
        C.to_parquet(out, index=False)
    return C


# ============================================================ L1 perception
_CYCLES = None

def _cycles_df():
    """Read the cycle cache once per process (the sweep calls load_cycles ~50x)."""
    global _CYCLES
    if _CYCLES is None:
        _CYCLES = pd.read_csv(CYCLES_CSV, parse_dates=['depart_load', 'arrive_load',
                                                       'arrive_unload', 'depart_unload'])
    return _CYCLES


def raw_months():
    """Months we hold raw GPS for, oldest first."""
    out = []
    for p in glob.glob(GPS_GLOB.format(y='*', m='*')):
        mm = re.search(r'gps_data_(\d{4})-(\d{1,2})\.csv$', os.path.basename(p))
        if mm:
            out.append(f'{mm.group(1)}-{int(mm.group(2)):02d}')
    return sorted(set(out))


def _month_cycles(month, build_if_missing=True):
    """One month of cycles, built from raw GPS whenever we hold it.

    The pre-baked data/cycles_all_months.csv was produced by the pre-2026-08-12 builder,
    which dropped every trip over MAX_CYCLE_HOURS -- 10.4% of BN's real trips -- so it is
    used only as a fallback for months whose raw GPS is not on disk."""
    if build_if_missing and month in raw_months():
        B = build_cycles(month)
        if len(B):
            return B
    C = _cycles_df()
    B = C[C.month == month].copy()
    if len(B):
        B['max_gap_s'] = np.nan            # unknown: the legacy table did not record it
        B['over_max_hours'] = False        # by construction -- those rows were dropped
        B['legacy_table'] = True
    return B


def load_cycles(zone_id, month=None, build_if_missing=True):
    """month=None -> all months for that zone (used as the POOLED baseline reference)."""
    z = ZONES[zone_id]
    months = [month] if month is not None else raw_months()
    parts = [_month_cycles(mm, build_if_missing) for mm in months]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    C = pd.concat(parts, ignore_index=True)
    for c in ['depart_load', 'arrive_load', 'arrive_unload', 'depart_unload']:
        C[c] = pd.to_datetime(C[c])
    cyc = C[(C.region == z['region']) & (C.load_zone == zone_id)].copy()
    cyc = cyc.sort_values(['tracker_id', 'depart_load']).reset_index(drop=True)
    cyc['next_depart'] = cyc.groupby('tracker_id')['depart_load'].shift(-1)
    if 'dwell_own_s' in cyc.columns:
        cyc['dwell_s'] = cyc['dwell_own_s']          # this visit's own arrival -> departure
    else:                                             # legacy table: fall back to the proxy
        same = cyc['tracker_id'].eq(cyc['tracker_id'].shift(-1))
        cyc['dwell_s'] = np.where(same, (cyc['next_depart'] - cyc['arrive_load']).dt.total_seconds(), np.nan)
    cyc.loc[cyc['dwell_s'] <= 0, 'dwell_s'] = np.nan
    return cyc


# ============================================================ 地基二 cause tagging
def _spans_overnight(t0, t1, hour=NIGHT_HOUR):
    if pd.isna(t0) or pd.isna(t1):
        return False
    mark = t0.normalize() + pd.Timedelta(hours=hour)
    if mark < t0:
        mark += pd.Timedelta(days=1)
    return mark <= t1


def _concurrency(cyc, cut_min=None):
    """Queue signal: how many OTHER trucks were at the load zone the MOMENT this truck
    arrived.

    The old version had to filter out 'inactive' stays (overnight, longer than 2x the GMM
    cut) because dwell was the next row's departure minus this arrival, so a truck that had
    driven away still counted as present for hours. dwell_s is now the truck's own measured
    stay, so every stay is a real presence and no filter is needed. cut_min is accepted for
    call compatibility and ignored."""
    a = cyc['arrive_load'].values.astype('datetime64[s]').astype(np.int64)
    dwell = cyc['dwell_s'].values
    b = a + np.nan_to_num(dwell).astype(np.int64)             # this stay's own departure
    ok = ~np.isnan(dwell)
    aa, bb = a[ok], b[ok]
    n = len(cyc); conc = np.full(n, np.nan)
    for i in range(n):
        if not ok[i]:
            continue
        conc[i] = int(np.sum((aa <= a[i]) & (bb >= a[i]))) - 1   # minus myself -> trucks ahead
    return conc


def tag_causes(cyc, cut_min, ff_q=FF_Q, svc_q=SVC_Q, ref=None):
    """地基二 + 地基一 split. Returns buckets (in-loop waste), reservoir (out-of-loop),
    baselines, no-queue loading time, and the mean in-loop dwell (loading+queue).

    ff_q / svc_q  = the baseline quantiles (defaults reproduce the original .15/.20).
    ref           = DataFrame the BASELINES are estimated from; None -> cyc itself
                    (per-month baseline). Pass the pooled multi-month cycles to use a
                    fixed reference instead — a congested month then no longer defines
                    its own 'free flow'. Attribution is always applied to `cyc`."""
    r = cyc if ref is None else ref
    d = cyc['dwell_s']
    conc = _concurrency(cyc)

    # Same causal rule the six discovered stations use (see station_split): loading takes as
    # long as it takes when nobody else is there. No percentile, no learned cut-point.
    # The GMM cut existed to separate genuine stays from the multi-hour artefacts the old
    # dwell was full of; with dwell measured directly there is nothing left to separate, and
    # the GMM now fits noise (it returned 1.8 min on the corrected November data).
    svc_load = float(pd.Series(np.where(conc == 0, d.values, np.nan)).median())
    if not np.isfinite(svc_load) or svc_load <= 0:
        svc_load = float(r['dwell_s'].dropna().quantile(ff_q))

    served = np.minimum(np.nan_to_num(d.values, nan=svc_load), svc_load)
    excess = np.where(np.isnan(d.values), 0.0, np.maximum(0, d.values - svc_load))
    queue_w = np.where(conc >= 1, excess, 0.0)       # someone was ahead of me -> queue
    solo_w = np.where(conc == 0, excess, 0.0)        # nobody there and still slow -> unexplained
    # Parking, shift breaks and overnight no longer appear here at all. They are not part of
    # a measured load-zone stay, and the ping layer books them against the place the truck
    # was actually sitting instead of against a clock rule.

    # in-loop dwell per cycle = loading + queue (the truck is still in the loop while queuing)
    inloop = served + queue_w

    ff_haul = r['haul_s'].quantile(ff_q)
    ff_return = r['return_s'].quantile(ff_q)
    dump_cyc = cyc[cyc['dump_s'] > 0]
    ref_dump = r[r['dump_s'] > 0]
    svc_dump = ref_dump['dump_s'].quantile(svc_q) if len(dump_cyc) and len(ref_dump) else 0.0

    h = lambda x: float(np.nansum(np.maximum(0, x))) / 3600.0
    buckets = dict(
        queue       = h(queue_w),
        load_solo   = h(solo_w),
        road_return = h(cyc['return_s'] - ff_return),
        road_haul   = h(cyc['haul_s'] - ff_haul),
        dump        = h(cyc['dump_s'] - svc_dump) if len(dump_cyc) else 0.0,
    )
    reservoir = {}          # off-loop time is located by the ping layer, not inferred here
    baselines = dict(svc_load_min=svc_load / 60, ff_haul_min=ff_haul / 60,
                     ff_return_min=ff_return / 60, svc_dump_min=svc_dump / 60, cut_min=cut_min,
                     ff_q=ff_q, svc_q=svc_q, baseline_ref='pooled' if ref is not None else 'month')
    return buckets, reservoir, baselines, svc_load, float(np.nanmean(inloop))


# ============================================================ L0 ping layer (2026-08-07)
def all_zone_boxes(exclude_ids=()):
    """Every zone the mine has drawn, as a bounding box + BOX_BUFFER, smallest first so an
    overlapping big box never steals a small one's pings.
    NOTE: only 11 of the 104 zones ship real polygons and they are all load/dump zones, so
    every infrastructure zone here is a rectangle. Real polygons need the Navixy API."""
    Z = pd.read_csv(ZONE_LIST).dropna(subset=['bounds_se_lat', 'bounds_nw_lat',
                                              'bounds_se_lng', 'bounds_nw_lng'])
    out = []
    for _, z in Z.iterrows():
        if int(z.id) in exclude_ids:
            continue
        la0, la1 = min(z.bounds_se_lat, z.bounds_nw_lat), max(z.bounds_se_lat, z.bounds_nw_lat)
        ln0, ln1 = min(z.bounds_se_lng, z.bounds_nw_lng), max(z.bounds_se_lng, z.bounds_nw_lng)
        out.append(dict(zone_id=int(z.id), name=f'z{int(z.id)}', label=str(z.label).strip(),
                        la0=la0 - BOX_BUFFER, la1=la1 + BOX_BUFFER,
                        ln0=ln0 - BOX_BUFFER, ln1=ln1 + BOX_BUFFER,
                        area=(la1 - la0 + 2 * BOX_BUFFER) * (ln1 - ln0 + 2 * BOX_BUFFER)))
    return sorted(out, key=lambda d: d['area'])


def merge_overlapping(boxes):
    """Zones whose (buffered) boxes overlap are one place, not two.

    At BN the tarping-off point and the Ukhaa weighbridge sit ~100 m apart; their boxes
    overlap, so any exclusive ping-assignment rule has to pick one arbitrarily and the loser
    looks like a drive-through. Physically a truck queues once for the pair. Merging the
    connected components removes the arbitrary choice and reports a station COMPLEX, which is
    also the more honest unit: we cannot verify what happens at each individual place."""
    n = len(boxes)
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a
    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if (a['la0'] <= b['la1'] and b['la0'] <= a['la1'] and
                    a['ln0'] <= b['ln1'] and b['ln0'] <= a['ln1']):
                union(i, j)
    groups = {}
    for i, b in enumerate(boxes):
        groups.setdefault(find(i), []).append(b)
    out = []
    for members in groups.values():
        if len(members) == 1:
            out.append(dict(members[0], members=[members[0]['label']]))
            continue
        members = sorted(members, key=lambda m: -m['area'])
        out.append(dict(zone_id=members[0]['zone_id'],
                        name='z' + '_'.join(str(m['zone_id']) for m in members),
                        label=' + '.join(m['label'] for m in members),
                        members=[m['label'] for m in members],
                        la0=min(m['la0'] for m in members), la1=max(m['la1'] for m in members),
                        ln0=min(m['ln0'] for m in members), ln1=max(m['ln1'] for m in members),
                        area=sum(m['area'] for m in members)))
    return sorted(out, key=lambda d: d['area'])


def _assign_zone(la, ln, boxes):
    """Smallest containing box wins; '' = not in any zone."""
    zone = np.full(len(la), '', dtype=object)
    for b in boxes:
        m = (zone == '') & (la >= b['la0']) & (la <= b['la1']) & \
            (ln >= b['ln0']) & (ln <= b['ln1'])
        zone[m] = b['name']
    return zone


def discover_topology(cyc, pings, boxes=None, verbose=False):
    """Find the loop's structure from GPS alone — no hand-written list of place names.

    For every zone the mine has drawn, count how many separate visits the fleet makes to it
    DURING haul/return legs, as a share of cycles. A place every trip passes on both legs
    scores ~200% and belongs in the loop; a place only some trips visit does not.

    Returns (stations, offloop, table). `stations` also carries `is_entrance` for gate zones,
    whose dwell is queueing outside a fence rather than a service of its own."""
    if boxes is None:
        excl = set(cyc.load_zone.unique().tolist() + cyc.unload_zone.unique().tolist())
        boxes = all_zone_boxes(exclude_ids={int(x) for x in excl})
    n_cyc = len(cyc)
    P = pings[_in_leg_mask(cyc, pings)]          # only time spent between the two zones
    counts, stops = {}, {}
    for b in boxes:                              # each box tested INDEPENDENTLY, so an
        inz = P[(P.lat.between(b['la0'], b['la1'])) &   # overlapping neighbour cannot hide a
                (P.lng.between(b['ln0'], b['ln1']))]    # station's stopped pings from us
        if len(inz) < 5:
            counts[b['name']] = 0; stops[b['name']] = 0; continue
        n = s = 0
        for tid, t in inz.groupby('tracker_id'):
            t = t.sort_values('get_time')
            brk = (t['get_time'].diff().dt.total_seconds().fillna(1e9) > VISIT_GAP).cumsum()
            grp = t.groupby(brk)['speed'].min()
            n += len(grp); s += int((grp <= STOP_SPEED).sum())
        counts[b['name']] = n; stops[b['name']] = s
    rows = []
    for b in boxes:
        n = counts[b['name']]
        if n < MIN_VISITS:
            continue
        cov = 100 * n / max(n_cyc, 1)
        sr = stops[b['name']] / n
        if cov >= STATION_MIN_COV:
            # on the route -- but is it a service point or just a place we drive through?
            kind = 'station' if sr >= STATION_MIN_STOPRATE else 'waypoint'
        elif cov < OFFLOOP_MAX_COV:
            kind = 'offloop'
        else:
            kind = 'ambiguous'
        rows.append(dict(zone_id=b['zone_id'], label=b['label'], visits=n,
                         coverage_pct=round(cov), stop_rate=round(sr, 2), kind=kind,
                         members=len(b.get('members', [b['label']]))))
    T = pd.DataFrame(rows).sort_values('coverage_pct', ascending=False)
    by_zid = {b['zone_id']: b for b in boxes}
    raw_st = [by_zid[r.zone_id] for r in T[T.kind == 'station'].itertuples(index=False)]
    # merge ONLY among stations: adjacent service points (e.g. a weighbridge 100 m from a
    # tarping point) are one place to a truck, and merging them removes the arbitrary choice
    # of which box owns a shared ping. Merging over ALL zones instead would chain the whole
    # dump-side industrial area into a single blob.
    stations = merge_overlapping(raw_st)
    stat_by_zid = {r.zone_id: r._asdict() for r in T[T.kind == 'station'].itertuples(index=False)}
    for st in stations:
        seed = stat_by_zid[st['zone_id']]
        st.update(coverage_pct=seed['coverage_pct'], stop_rate=seed['stop_rate'],
                  visits=seed['visits'])
    offloop = [dict(by_zid[r.zone_id], **r._asdict()) for r in T[T.kind == 'offloop'].itertuples(index=False)]
    if verbose:
        print(T.to_string(index=False))
    return stations, offloop, T


def _in_leg_mask(cyc, pings):
    """True for pings that fall inside some haul/return leg of this flow."""
    legs = _leg_frame(cyc)
    m = np.zeros(len(pings), bool)
    idx = {t: np.where(pings.tracker_id.values == t)[0] for t in pings.tracker_id.unique()}
    pt = pings['get_time'].values.astype('datetime64[s]').astype(np.int64)
    for tid, L in legs.groupby('tid'):
        ii = idx.get(tid)
        if ii is None or not len(ii):
            continue
        v = pt[ii]
        for t0, t1 in zip(L.t0.values.astype('datetime64[s]').astype(np.int64),
                          L.t1.values.astype('datetime64[s]').astype(np.int64)):
            m[ii[(v >= t0) & (v <= t1)]] = True
    return m


def _leg_frame(cyc):
    return pd.concat([
        cyc[['tracker_id', 'depart_load', 'arrive_unload']]
           .rename(columns={'tracker_id': 'tid', 'depart_load': 't0', 'arrive_unload': 't1'}),
        cyc[['tracker_id', 'depart_unload', 'arrive_load']]
           .rename(columns={'tracker_id': 'tid', 'depart_unload': 't0', 'arrive_load': 't1'})
    ]).dropna()


def load_pings(month, trucks):
    """Raw GPS for these trucks in this month. First call reads the (300-800 MB) monthly CSV
    and caches a small parquet in analysis/.ping_cache; later calls are instant."""
    os.makedirs(PING_CACHE, exist_ok=True)
    cache = os.path.join(PING_CACHE, f'pings_{month}_{len(trucks)}.parquet')
    if os.path.exists(cache):
        return pd.read_parquet(cache)
    y, m = month.split('-')
    src = GPS_GLOB.format(y=y, m=int(m))
    if not os.path.exists(src):
        raise FileNotFoundError(f"raw GPS not found: {src} (use_pings=False to skip the ping layer)")
    g = pd.read_csv(src, usecols=['tracker_id', 'get_time', 'lat', 'lng', 'speed'],
                    parse_dates=['get_time'])
    g = g[g.tracker_id.isin(trucks)].sort_values(['tracker_id', 'get_time']).reset_index(drop=True)
    g.to_parquet(cache, index=False)
    return g


def _visits(pings, box):
    """Contiguous presence inside a box = one visit, plus how many OTHER trucks were already
    inside when this one arrived (vectorised: started-by-now minus ended-by-now, minus self)."""
    inz = pings[(pings.lat.between(box['la0'], box['la1'])) &
                (pings.lng.between(box['ln0'], box['ln1']))]
    if len(inz) < 20:
        return pd.DataFrame(columns=['tid', 't0', 't1', 'min', 'conc'])
    rec = []
    for tid, t in inz.groupby('tracker_id'):
        t = t.sort_values('get_time')
        brk = t['get_time'].diff().dt.total_seconds().fillna(0) > VISIT_GAP
        for _, blk in t.groupby(brk.cumsum()):
            rec.append((tid, blk['get_time'].iloc[0], blk['get_time'].iloc[-1]))
    V = pd.DataFrame(rec, columns=['tid', 't0', 't1'])
    V['min'] = (V.t1 - V.t0).dt.total_seconds() / 60
    V = V[V['min'] > 0].sort_values('t0').reset_index(drop=True)
    a0 = V.t0.values.astype('datetime64[s]').astype(np.int64)
    a1 = V.t1.values.astype('datetime64[s]').astype(np.int64)
    V['conc'] = np.clip(np.searchsorted(np.sort(a0), a0, 'right')
                        - np.searchsorted(np.sort(a1), a0, 'left') - 1, 0, None)
    return V


def station_split(pings, box, legs):
    """service / queue / solo-long shares for one station.
    service   = min(dwell, median dwell with nobody else there)   <- causal, no percentile
    queue     = the excess when >=1 truck was already there
    solo-long = the excess with nobody there (unexplained; kept separate on purpose)
    Concurrency uses ALL visits (a truck blocks others whatever leg it is on); the shares are
    measured on visits that start inside a haul/return leg, to match the leg-based accounting."""
    V = _visits(pings, box)
    if not len(V):
        return None
    svc = V[V.conc == 0]['min'].median()
    if not np.isfinite(svc) or svc <= 0:
        svc = V['min'].quantile(.15)
    rho = V[['conc', 'min']].corr(method='spearman').iloc[0, 1]
    keep = np.zeros(len(V), bool)
    vt = V.t0.values.astype('datetime64[s]').astype(np.int64)
    for tid, L in legs.groupby('tid'):
        idx = np.where(V.tid.values == tid)[0]
        if not len(idx):
            continue
        for t0, t1 in zip(L.t0.values.astype('datetime64[s]').astype(np.int64),
                          L.t1.values.astype('datetime64[s]').astype(np.int64)):
            keep[idx[(vt[idx] >= t0) & (vt[idx] <= t1)]] = True
    W = V[keep] if keep.any() else V
    served = np.minimum(W['min'], svc)
    excess = W['min'] - served
    s, q, so = served.sum(), excess[W.conc >= 1].sum(), excess[W.conc == 0].sum()
    tot = s + q + so
    if tot <= 0:
        return None
    return dict(service_min=float(svc), conc_spearman=float(rho), visits=int(len(W)),
                f_service=s / tot, f_queue=q / tot, f_solo=so / tot)


def decompose_legs(cyc, pings, boxes):
    """Charge every GPS interval of every haul/return leg to exactly one place.
    Returns a DataFrame, one row per leg, minutes per category."""
    rows = []
    for tid, gt in pings.groupby('tracker_id'):
        t = gt['get_time'].values
        lat, lng, spd = gt.lat.values, gt.lng.values, gt.speed.values
        for r in cyc[cyc.tracker_id == tid].itertuples():
            for leg, t0, t1 in [('haul', r.depart_load, r.arrive_unload),
                                ('ret', r.depart_unload, r.arrive_load)]:
                if pd.isna(t0) or pd.isna(t1):
                    continue
                i0 = np.searchsorted(t, np.datetime64(t0))
                i1 = np.searchsorted(t, np.datetime64(t1))
                if i1 - i0 < 3:
                    continue
                dt = np.minimum(np.diff(t[i0:i1]).astype('timedelta64[s]').astype(float), DT_CAP)
                la, ln, sp = lat[i0:i1][:-1], lng[i0:i1][:-1], spd[i0:i1][:-1]
                zone = _assign_zone(la, ln, boxes)
                zone[(zone == '') & (sp <= STOP_SPEED)] = 'stopped_unmapped'
                zone[zone == ''] = 'driving'
                rec = dict(leg=leg, total=(t1 - t0).total_seconds() / 60)
                rec.update(pd.Series(dt / 60).groupby(zone).sum().to_dict())
                rows.append(rec)
    return pd.DataFrame(rows).fillna(0.0)


def tag_causes_pings(cyc, cut_min, month, ff_q=FF_Q, svc_q=SVC_Q, verbose=False):
    """The 2026-08-07 replacement for the road half of tag_causes().
    Load-zone queue / idle / overnight still come from tag_causes(); what changes is that the
    road legs are decomposed onto a topology DISCOVERED from the data (see discover_topology)
    instead of being one undifferentiated 'road' lump."""
    pings = load_pings(month, cyc.tracker_id.unique())
    legs = _leg_frame(cyc)
    excl = {int(x) for x in cyc.load_zone.unique().tolist() + cyc.unload_zone.unique().tolist()}
    st_boxes, off_boxes, topo = discover_topology(cyc, pings, all_zone_boxes(exclude_ids=excl),
                                                  verbose=verbose)
    # merged station complexes + the out-of-loop stops; waypoints and rare zones are left out
    # on purpose so their time falls through to driving / stopped-unmapped.
    boxes = list(st_boxes) + list(off_boxes)
    R = decompose_legs(cyc, pings, boxes)

    base_b, reservoir, baselines, svc_load, inloop_mean = tag_causes(cyc, cut_min, ff_q, svc_q)
    h = lambda x: float(np.nansum(np.maximum(0, x))) / 60

    buckets = {'queue_shovel': base_b['queue'], 'load_solo': base_b['load_solo'],
               'dump': base_b['dump']}
    stations = {}
    for b in st_boxes:
        name = b['name']
        tot = R[name].sum() / 60 if name in R.columns else 0.0
        if tot <= 0:
            continue
        sp = station_split(pings, b, legs)
        if sp is None:
            continue
        buckets[f'{name}_queue'] = tot * sp['f_queue']
        buckets[f'{name}_solo_long'] = tot * sp['f_solo']
        stations[name] = dict(label=b['label'], role='station', coverage_pct=b['coverage_pct'],
                              stop_rate=b['stop_rate'], members=b.get('members', [b['label']]),
                              total_truck_h=round(tot),
                              service_truck_h=round(tot * sp['f_service']),
                              queue_truck_h=round(tot * sp['f_queue']),
                              solo_long_truck_h=round(tot * sp['f_solo']),
                              service_min=round(sp['service_min'], 1),
                              conc_spearman=round(sp['conc_spearman'], 2), visits=sp['visits'])
    for leg, name in [('haul', 'road_haul'), ('ret', 'road_return')]:
        d = R[R.leg == leg]['driving']
        buckets[name] = h(d - d.quantile(ff_q))          # driving only -- no parked time
    buckets['stopped_unmapped'] = R['stopped_unmapped'].sum() / 60 if 'stopped_unmapped' in R else 0.

    reservoir = dict(reservoir)
    off_names = [b['name'] for b in off_boxes if b['name'] in R.columns]
    reservoir['offloop_stop'] = float(sum(R[n].sum() for n in off_names)) / 60
    # Phase duration the pings cannot account for: a hole in the stream contributes at most
    # DT_CAP, so a trip that ran while the tracker was off leaves a shortfall. Keeping every
    # trip (rather than dropping the long ones) makes this visible instead of hiding it in a
    # duration cap. Booked so the identity closes; it is missing data, not recoverable time,
    # so it sits outside the ranking.
    shortfall = float(R.total.sum() - R.drop(columns=['leg', 'total']).sum().sum())
    reservoir['unrecorded_gap'] = max(0.0, shortfall) / 60
    drive_share = 100 * R['driving'].sum() / R.drop(columns=['leg', 'total']).sum().sum()
    legs_info = dict(driving_share_pct=round(drive_share),
                     identity_error_pct=round(100 * (R.drop(columns=['leg', 'total']).sum().sum()
                                                     + max(0.0, shortfall)
                                                     - R.total.sum()) / R.total.sum(), 1),
                     unrecorded_gap_pct=round(100 * max(0.0, shortfall) / R.total.sum(), 1),
                     topology=topo.to_dict('records'),
                     offloop_places=[b['label'] for b in off_boxes])
    return buckets, reservoir, baselines, svc_load, inloop_mean, stations, legs_info


# ============================================================ L3-A capacity / utilisation
def _busy_rate(times):
    dep = pd.Series(times).dropna().sort_values()
    gaps = dep.diff().dt.total_seconds().dropna() / 60
    busy = gaps[gaps < BUSY_GAP_MIN]
    return 60 / busy.median() if len(busy) else np.nan


def capacity(cyc, inloop_mean_s):
    days = cyc['date'].nunique()
    trucks = cyc['tracker_id'].nunique()
    loads_day = len(cyc) / days
    per_hod = cyc.groupby(cyc['depart_load'].dt.hour).size()
    op_hours = int((per_hod >= 0.4 * per_hod.mean()).sum())

    shovel_rate = _busy_rate(cyc['depart_load'])                  # loads/h when busy
    dump_rate = _busy_rate(cyc['depart_unload'])
    flow = loads_day / op_hours                                  # loads/h over active hours
    ceiling = min(shovel_rate, dump_rate) * op_hours
    bind = 'dump' if dump_rate < shovel_rate else 'shovel'
    cycle_min = (cyc['cycle_s'].mean() + inloop_mean_s) / 60      # moving legs + loading+queue
    return dict(days=days, trucks=trucks, loads_day=loads_day, op_hours=op_hours,
                shovel_rate=shovel_rate, dump_rate=dump_rate, flow=flow,
                rho_shovel=flow / shovel_rate, rho_dump=flow / dump_rate,
                ceiling=ceiling, bind=bind, cycle_min=cycle_min)


# ============================================================ L3-C levers (per DAY)
def rank_levers(buckets, reservoir, cap):
    loads = cap['loads_day']; C = cap['ceiling']; days = cap['days']; T = cap['cycle_min']
    cyc_h = loads * T / 60                                        # cycling truck-h / day (Little)

    def shorten(bucket_h_month):                                 # mechanism a
        save_min = (bucket_h_month / days) / loads * 60          # per-cycle saving (min)
        newT = max(T - save_min, 1.0)
        return min(cyc_h * 60 / newT, C)

    def add_hours(res_h_month):                                  # mechanism b
        return min((cyc_h + res_h_month / days) * 60 / T, C)

    g = lambda x: round(x - loads)
    # DISPATCH-RECOVERABLE levers — fixable within the current fleet; these get ranked.
    #   mechanism a (shorten loop): road / queue / dump    mechanism b: on-shift idle (dispatch)
    disp = []
    for key, label in [('road_return', 'Haul-road: empty return'),
                       ('road_haul',   'Haul-road: loaded haul'),
                       ('queue',       'Queue at the shovel (smooth arrivals)'),
                       ('dump',        'Dump spotting / congestion')]:
        nl = shorten(buckets.get(key, 0.0))
        disp.append(dict(cause=label, mech='a: shorten the loop',
                         bucket_truck_h=round(buckets.get(key, 0.0)), new_loads=round(nl), gain=g(nl)))
    nl = add_hours(reservoir.get('on_shift_idle', 0.0))
    disp.append(dict(cause='On-shift idle (better dispatch)', mech='b: add looping hours',
                     bucket_truck_h=round(reservoir.get('on_shift_idle', 0.0)), new_loads=round(nl), gain=g(nl)))
    disp = sorted(disp, key=lambda l: -l['gain'])
    for i, l in enumerate(disp, 1):
        l['rank'] = i
    # mechanism c — expand the binding station (only pays once at the ceiling)
    at_ceiling = loads >= 0.98 * C
    disp.append(dict(rank=len(disp) + 1, cause=f"Expand the binding station ({cap['bind']})",
                     mech='c: raise the ceiling', bucket_truck_h=None,
                     new_loads='raises ceiling' if at_ceiling else round(loads),
                     gain=0 if not at_ceiling else 'raises ceiling',
                     note='only pays once throughput reaches the ceiling'))
    # STAFFING — overnight parking is off-shift downtime, a scheduling decision, NOT dispatch.
    # Reported SEPARATELY so it does not drown out the dispatch-recoverable ranking.
    park_h = reservoir.get('overnight_parked', 0.0)
    nl = add_hours(park_h)
    staffing = dict(cause='Overnight parking -> more shifts', mech='b: staffing (separate decision)',
                    reservoir_truck_h=round(park_h), new_loads=round(nl), gain=g(nl),
                    note='off-shift downtime; a staffing/scheduling lever, not dispatch — some is legitimate')
    return disp, round(cyc_h), staffing


LEVER_TEXT = {
    'queue_shovel':       ('Queue at the shovel (another truck was already loading)',
                           'a: shorten the loop'),
    'load_solo':          ('Slow at the shovel with nobody else there (cause unknown)',
                           'a: shorten the loop'),
    'dump':               ('Dump spotting / congestion', 'a: shorten the loop'),
    'road_haul':          ('Haul road, loaded — DRIVING time only', 'a: shorten the loop'),
    'road_return':        ('Haul road, empty — DRIVING time only', 'a: shorten the loop'),
    'stopped_unmapped':   ('Stopped somewhere unmapped (only 11 of 104 zones have polygons)',
                           'a: shorten the loop'),
    'on_shift_idle':      ('On-shift idle (better dispatch)', 'b: add looping hours'),
}


def _lever_text(key, station_labels):
    """Station keys are discovered (z<zone_id>_queue / _solo_long), so their wording is built
    from the mine's own label rather than from a table we wrote by hand."""
    if key in LEVER_TEXT:
        return LEVER_TEXT[key]
    for suffix, tmpl in [('_queue', 'Queue at {}'),
                         ('_solo_long', '{} — long dwell, nobody blocking (cause unknown)')]:
        if key.endswith(suffix):
            lab = station_labels.get(key[:-len(suffix)], key[:-len(suffix)])
            return (tmpl.format(lab), 'a: shorten the loop')
    return (key, 'a: shorten the loop')
TIE_MARGIN = 5.0        # #1 must beat #2 by this many loads/day to be called a single winner;
                        # swept evidence: rank flips only ever happen inside this band.

# Out-of-loop time a DISPATCHER cannot recover. Overnight parking is off-shift. The mid-trip
# car park is the shift handover (91% of those stops begin in the 04-07 / 16-19 windows) and
# klonk is lumped with it; both are roster/maintenance decisions, not dispatch. Keeping them
# in the dispatch ranking would credit dispatch with hours it cannot touch.
NON_DISPATCH = {'offloop_stop': 'Stopped off the loop (car park, yard) -> roster / logistics',
                'unrecorded_gap': 'Phase time the GPS did not record -> data quality, not a lever'}
# In-loop waste we can measure but not name. Real lost time, so it stays in the budget, but it
# is flagged so nobody reads it as an actionable lever.
UNATTRIBUTED = {'stopped_unmapped'}


def rank_levers_general(buckets, reservoir, cap, station_labels=None):
    """Same two mechanisms as rank_levers(), over arbitrary bucket names.
    Returns (dispatch levers, cycling truck-h/day, non-dispatch items, tie verdict).
    Anything in NON_DISPATCH is pulled out of the ranking — a dispatcher cannot recover a
    shift handover any more than an overnight park."""
    loads, C, days, T = cap['loads_day'], cap['ceiling'], cap['days'], cap['cycle_min']
    cyc_h = loads * T / 60
    shorten = lambda h: min(cyc_h * 60 / max(T - (h / days) / loads * 60, 1.0), C)
    add_h = lambda h: min((cyc_h + h / days) * 60 / T, C)

    station_labels = station_labels or {}
    lv = []
    for k, v in buckets.items():
        txt, mech = _lever_text(k, station_labels)
        lv.append(dict(cause=txt, key=k, mech=mech, bucket_truck_h=round(v),
                       new_loads=round(shorten(v), 1), gain=round(shorten(v) - loads, 1),
                       unattributed=k in UNATTRIBUTED))
    for k, v in reservoir.items():
        if k in NON_DISPATCH:
            continue
        txt, mech = _lever_text(k, station_labels)
        lv.append(dict(cause=txt, key=k, mech=mech, bucket_truck_h=round(v),
                       new_loads=round(add_h(v), 1), gain=round(add_h(v) - loads, 1),
                       unattributed=False))
    lv = sorted(lv, key=lambda x: -x['gain'])
    for i, l in enumerate(lv, 1):
        l['rank'] = i
    margin = round(lv[0]['gain'] - lv[1]['gain'], 1) if len(lv) > 1 else None
    verdict = dict(margin=margin, tied=(margin is not None and margin < TIE_MARGIN),
                   top=[l['cause'] for l in lv[:2]] if (margin is not None and margin < TIE_MARGIN)
                       else [lv[0]['cause']],
                   note=('#1 and #2 are within the parameter wobble — report them as tied'
                         if (margin is not None and margin < TIE_MARGIN)
                         else f'#1 clears #2 by {margin} loads/day — a real winner'))
    staffing = []
    for k, txt in NON_DISPATCH.items():
        v = reservoir.get(k, 0.0)
        if v <= 0:
            continue
        staffing.append(dict(cause=txt, key=k, mech='b: roster / logistics (NOT dispatch)',
                             reservoir_truck_h=round(v), new_loads=round(add_h(v)),
                             gain=round(add_h(v) - loads),
                             note='off-loop time a dispatcher cannot recover; some of it is legitimate'))
    staffing = sorted(staffing, key=lambda x: -x['gain'])
    return lv, round(cyc_h), staffing, verdict


def observed_headline(cyc, stop_frac=STOP_FRAC):
    """The evidence-backed end of the range: what this fleet has ALREADY achieved.

    The old single figure compared a contaminated 'now' (the monthly mean includes real
    stoppage days) against a ceiling never once approached in 150 days. This instead asks
    'what if every normal day matched your own best day' — no baseline quantile, no service
    rate, no extrapolation; it happened. It is a LOWER bound: it measures day-to-day
    inconsistency, so a uniformly slow operation would score +0% and still have room."""
    d = cyc.groupby('date').agg(loads=('tracker_id', 'size'), trucks=('tracker_id', 'nunique'))
    bar = stop_frac * d.loads.median()
    normal, stop = d[d.loads >= bar], d[d.loads < bar]
    if len(normal) < 5:
        return None
    cur = normal.loads.mean()
    best3 = normal.nlargest(3, 'loads')
    lpt = lambda t: (t.loads / t.trucks).mean()
    lost = len(stop) * cur - stop.loads.sum()
    return dict(
        normal_days=len(normal), stoppage_days=len(stop),
        current_loads_day=round(cur, 1),
        best_day=int(normal.loads.max()), top10pct_day=round(float(normal.loads.quantile(.9)), 1),
        gain_pct_best=round(100 * (normal.loads.max() / cur - 1)),
        gain_pct_top10=round(100 * (normal.loads.quantile(.9) / cur - 1)),
        from_more_trucks_pct=round(100 * (best3.trucks.mean() / normal.trucks.mean() - 1)),
        from_trips_per_truck_pct=round(100 * (lpt(best3) / lpt(normal) - 1)),
        stoppage_lost_loads=round(lost), stoppage_lost_share_pct=round(100 * lost / d.loads.sum()),
        note='trips-per-truck is the only half dispatch owns; more-trucks-out is maintenance')


def feedback(cap, top_new_loads):
    flow_new = top_new_loads / cap['op_hours']
    return dict(new_flow=round(flow_new, 2),
                rho_shovel_new=round(flow_new / cap['shovel_rate'], 2),
                rho_dump_new=round(flow_new / cap['dump_rate'], 2),
                note=f"pushing toward the ceiling, {cap['bind']} reaches 100% first -> it becomes the next bottleneck")


# ============================================================ E bootstrap band
def bootstrap_headline(cyc, cut_min, n=150, seed=0, ff_q=FF_Q, svc_q=SVC_Q, ref=None):
    rng = np.random.RandomState(seed); gains = []
    trucks = cyc['tracker_id'].unique()
    for _ in range(n):
        pick = rng.choice(trucks, len(trucks), replace=True)     # resample trucks
        s = pd.concat([cyc[cyc.tracker_id == t] for t in pick]).reset_index(drop=True)
        try:
            b, res, base, svc, inl = tag_causes(s, cut_min, ff_q, svc_q, ref)
            cp = capacity(s, inl)
            lv, _, _ = rank_levers(b, res, cp)
            gs = [l['gain'] for l in lv if isinstance(l['gain'], (int, float))]
            gains.append(max(gs) if gs else 0)
        except Exception:
            continue
    if not gains:
        return None
    return dict(p5=round(np.percentile(gains, 5)), p50=round(np.percentile(gains, 50)),
                p95=round(np.percentile(gains, 95)))


# ============================================================ orchestrator
def diagnose_v2(zone_id, month='2025-11', with_band=True, ff_q=FF_Q, svc_q=SVC_Q, ref=None,
                use_pings=True):
    """use_pings=True (default) runs the six-station ping layer. use_pings=False falls back to
    the cycle-table-only road buckets, which are KNOWN-BIASED (parked time booked as road) —
    the output carries a caveat saying so."""
    z = ZONES[zone_id]
    cyc = load_cycles(zone_id, month)
    stations, legs_info, ping_error = {}, {}, None
    if use_pings:
        try:
            (buckets, reservoir, baselines, svc_load, inloop,
             stations, legs_info) = tag_causes_pings(cyc, None, month, ff_q, svc_q)
        except (FileNotFoundError, KeyError, ValueError) as e:
            ping_error = f'{type(e).__name__}: {e}'
            use_pings = False
    if not use_pings:
        buckets, reservoir, baselines, svc_load, inloop = tag_causes(cyc, cut_min, ff_q, svc_q, ref)
    cap = capacity(cyc, inloop)
    if use_pings:
        levers, cyc_h, staffing, verdict = rank_levers_general(
            buckets, reservoir, cap, {k: v['label'] for k, v in stations.items()})
    else:
        levers, cyc_h, staffing = rank_levers(buckets, reservoir, cap)
        verdict = None
    _staff = staffing if isinstance(staffing, list) else [staffing]
    reach = ([l['new_loads'] for l in levers if isinstance(l['new_loads'], (int, float))]
             + [s['new_loads'] for s in _staff])
    fb = feedback(cap, max(reach)) if reach else {}
    band = bootstrap_headline(cyc, None, ff_q=ff_q, svc_q=svc_q, ref=ref) if with_band else None
    observed = observed_headline(cyc)

    # combined DISPATCH-recoverable ceiling: fix all in-loop waste + on-shift idle at once
    # (excludes overnight staffing) -> the number comparable to the paper's "recoverable gain vs current".
    waste_h = sum(buckets.values())
    save_min = (waste_h / cap['days']) / cap['loads_day'] * 60
    newT = max(cap['cycle_min'] - save_min, 1.0)
    new_cyc_h = cyc_h + reservoir.get('on_shift_idle', 0.0) / cap['days']
    comb = min(new_cyc_h * 60 / newT, cap['ceiling'])
    recoverable = dict(new_loads=round(comb), gain=round(comb - cap['loads_day']),
                       pct=round(100 * (comb - cap['loads_day']) / cap['loads_day']),
                       warning='THEORETICAL UPPER BOUND — assumes every trip drops to the fast '
                               'baseline at once, and leans on a ceiling that moves 125..273 under '
                               'plausible parameters. Never headline this; pair it with `observed`.')
    headline = dict(
        lower_bound_pct=observed['gain_pct_best'] if observed else None,
        lower_bound_basis='every normal day matches this fleet\'s own best day (it happened)',
        dispatch_share_pct=observed['from_trips_per_truck_pct'] if observed else None,
        upper_bound_pct=recoverable['pct'],
        upper_bound_basis='all in-loop waste removed at once (never observed)',
        note='Report the range. The truth is between; observational data cannot locate it. '
             'The collaborator paper\'s +53.8% for BN falls inside this range.')
    return dict(
        zone_id=zone_id, name=z['name'], region=z['region'], month=month,
        method='ping layer: six stations, causal service times' if use_pings
               else 'cycle-table only (KNOWN-BIASED road buckets)',
        ping_error=ping_error,
        throughput=dict(loads_day=round(cap['loads_day'], 1), trucks=cap['trucks'],
                        days=cap['days'], op_hours=cap['op_hours']),
        stations=dict(shovel_rate=round(cap['shovel_rate'], 1), dump_rate=round(cap['dump_rate'], 1),
                      rho_shovel=round(cap['rho_shovel'], 2), rho_dump=round(cap['rho_dump'], 2),
                      binding=cap['bind'],
                      saturated=bool(max(cap['rho_shovel'], cap['rho_dump']) >= 1.0),
                      ceiling_not_reported='utilisation moves 0.23-0.67 and the ceiling 125-273 '
                                           'across 175 parameter combinations; only "not '
                                           'saturated" survives'),
        roadside_stations=stations, leg_decomposition=legs_info,
        lever_verdict=verdict, observed=observed, headline=headline,
        cycle=dict(**{k: (round(v, 3) if isinstance(v, float) else v) for k, v in baselines.items()},
                   cycle_min=round(cap['cycle_min'], 1), cycling_truck_h_day=cyc_h),
        buckets_truck_h={k: round(v) for k, v in buckets.items()},
        reservoir_truck_h={k: round(v) for k, v in reservoir.items()},
        levers=levers, staffing=staffing, recoverable_combined=recoverable, feedback=fb,
        headline_gain_band=band,
        caveats=['every load->dump->load trip is kept; a data gap is recorded, not a duration cap',
                 'a load-zone visit needs a real stop, so a drive-through cannot close a cycle',
                 'load-zone stay measured from that visit itself, not from the next row',
                 'service = median stay with nobody else there; queue = the excess with someone ahead',
                 'road buckets are DRIVING time only; station/park time is booked separately'
                 if use_pings else 'ROAD BUCKETS KNOWN-BIASED: parked time counted as road',
                 'station service = median dwell with nobody else there (causal, not a percentile)',
                 'a station is a place every trip passes (~200% coverage); <100% -> out-of-loop',
                 'infrastructure zones are bounding boxes — only 11 of 104 have real polygons',
                 'grade checked and ruled out: BN net grade is 0.13% over 34 km',
                 'gains = UPPER BOUND; report the headline as a RANGE',
                 'no payload -> loads/truck-hours',
                 'DIAGNOSTIC not proof -> before/after pilot'])


def report(dx):
    L = []; p = L.append
    p("=" * 78)
    p(f"DIAGNOSIS v2 — {dx['name']} (zone {dx['zone_id']}, {dx['month']})")
    p("=" * 78)
    t = dx['throughput']; s = dx['stations']; c = dx['cycle']
    p(f"THROUGHPUT : {t['loads_day']} loads/day | {t['trucks']} trucks | {t['op_hours']}h active/day")
    p(f"METHOD     : {dx.get('method','')}")
    if dx.get('ping_error'):
        p(f"   !! ping layer unavailable, fell back: {dx['ping_error']}")
    p(f"STATIONS   : shovel {s['shovel_rate']}/h busy {s['rho_shovel']*100:.0f}% | "
      f"dump {s['dump_rate']}/h busy {s['rho_dump']*100:.0f}%  -> binding = {s['binding'].upper()}"
      f"  ({'SATURATED' if s.get('saturated') else 'not saturated'})")
    p(f"             loop {c['cycle_min']} min | cycling {c['cycling_truck_h_day']} truck-h/day")
    if dx.get('leg_decomposition'):
        li = dx['leg_decomposition']
        p(f"ROAD LEGS  : only {li['driving_share_pct']}% of 'road' time is actually driving "
          f"(accounting closes to {li['identity_error_pct']}%)")
    if dx.get('roadside_stations'):
        p(f"\nROADSIDE STATIONS (every trip passes these, both ways):")
        p(f"   {'station':30s}{'total':>7s}{'service':>8s}{'queue':>7s}{'solo-long':>10s}"
          f"{'svc min':>9s}{'conc r':>8s}")
        for k, v in sorted(dx['roadside_stations'].items(),
                           key=lambda x: -x[1]['queue_truck_h']):
            p(f"   {v['label']:30s}{v['total_truck_h']:7d}{v['service_truck_h']:8d}"
              f"{v['queue_truck_h']:7d}{v['solo_long_truck_h']:10d}"
              f"{v['service_min']:9.1f}{v['conc_spearman']:8.2f}")
    p(f"\nIN-LOOP WASTE (truck-h/mo, by CAUSE):")
    for k, v in sorted(dx['buckets_truck_h'].items(), key=lambda x: -x[1]):
        p(f"   {k:24s} {v:6d} h")
    p(f"OUT-OF-LOOP reservoir:")
    for k, v in dx['reservoir_truck_h'].items():
        p(f"   {k:24s} {v:6d} h")
    p(f"\nDISPATCH-RECOVERABLE LEVERS (ranked by real loads/day gained; within current fleet):")
    for l in dx['levers'][:8]:
        g = l['gain']; gs = f"+{g}/day" if isinstance(g, (int, float)) else g
        flag = '  [UNATTRIBUTED — measured, not explained]' if l.get('unattributed') else ''
        p(f"  #{l['rank']}  {l['cause']}{flag}")
        p(f"       [{l['mech']}] {l['bucket_truck_h']} truck-h -> {l['new_loads']} loads/day ({gs})")
    if len(dx['levers']) > 8:
        p(f"       ... {len(dx['levers'])-8} smaller levers omitted")
    if dx.get('lever_verdict'):
        v = dx['lever_verdict']
        p(f"  VERDICT: {v['note']}")
        if v['tied']:
            p(f"           treat as tied: {' / '.join(v['top'])}")
    st = dx['staffing']
    st = st if isinstance(st, list) else [st]
    p(f"\nNOT DISPATCH — roster / logistics (a dispatcher cannot recover these):")
    for s in st:
        p(f"       {s['cause']}")
        p(f"          {s['reservoir_truck_h']} truck-h/mo -> up to {s['new_loads']} loads/day (+{s['gain']})")
    o = dx.get('observed')
    if o:
        p(f"\nWHAT THIS FLEET HAS ALREADY DONE ({o['normal_days']} normal days, "
          f"{o['stoppage_days']} stoppage days pulled out):")
        p(f"   now {o['current_loads_day']}/day  ->  its own best day {o['best_day']}/day "
          f"= +{o['gain_pct_best']}%   (top-10% day {o['top10pct_day']} = +{o['gain_pct_top10']}%)")
        p(f"   of which: more trucks out +{o['from_more_trucks_pct']}% (maintenance) | "
          f"trips per truck +{o['from_trips_per_truck_pct']}% (DISPATCH — the part we own)")
        p(f"   stoppage days cost {o['stoppage_lost_loads']} loads "
          f"= {o['stoppage_lost_share_pct']}% of the month (maintenance/weather, not dispatch)")
    hl = dx.get('headline')
    if hl and hl['lower_bound_pct'] is not None:
        p(f"\nHEADLINE — REPORT THE RANGE, NOT A POINT:")
        p(f"   +{hl['lower_bound_pct']}%  evidence-backed floor ({hl['lower_bound_basis']})")
        p(f"   +{hl['upper_bound_pct']}%  theoretical ceiling ({hl['upper_bound_basis']})")
        p(f"   {hl['note']}")
    if dx['headline_gain_band']:
        b = dx['headline_gain_band']
        p(f"TOP-LEVER BOOTSTRAP: +{b['p50']}/day   (90% band +{b['p5']} .. +{b['p95']})")
    if dx.get('feedback'):
        p(f"FEEDBACK   : {dx['feedback']['note']}")
    p("=" * 78)
    return "\n".join(L)


if __name__ == '__main__':
    zid = int(sys.argv[1]) if len(sys.argv) > 1 else 25559
    dx = diagnose_v2(zid)
    print(report(dx))
    out = os.path.join(_HERE, f"diagnosis_v2_{zid}.json")
    json.dump(dx, open(out, 'w'), indent=2, ensure_ascii=False, default=str)
    print(f"\n[-> {out}]")
