#!/usr/bin/env python3
"""
Diagnostic agent core  —  diagnose(zone_id, month) -> structured diagnosis dict.

Integrates the four-layer framework (PROJECT_HANDOFF §7), everything BEFORE the LLM:
    L1 perception    -> cycles + cycle decomposition + loading dwell   (perception)
    L2 attribution   -> recoverable truck-hours per cause bucket       (attribution)
    L3a capacity     -> service rate, utilisation, shovel ceiling      (capacity, ToC §9)
    L3b decision     -> binding constraint + REALISTIC what-if ceilings (decide)
    L3c recommend    -> constraint/bucket -> literature-backed lever    (recommend)
The returned dict is what the L4 LLM layer (agent_explain.py) narrates.

Self-contained on data/cycles_all_months.csv.  Generalises across load zones
(config-driven) so the SAME code diagnoses BN and Middling differently.

Idle model (2026-07-22): the loading dwell is split at TWO lines —
  svc_load(p20) .. QUEUE_CAP(120min) = load_queue     (waiting at the shovel)
  QUEUE_CAP .. PARK_CAP(6h)          = idle_onshift    (on-shift idle, recoverable-ish)
  > PARK_CAP                          = downtime        (off-shift/parked, NOT dispatch-recoverable)
The realistic what-if ceiling KEEPS the actual fleet availability and credits only faster
ACTIVE cycling (removing queue + road waste). Running more truck-hours (cutting downtime) is a
SEPARATE staffing lever whose ceiling is the shovel.

Honesty frame: DIAGNOSTIC, not an optimiser. Recoverable hours are UPPER BOUNDS; "throughput
effect" is a what-if ceiling, not a proven gain — proving a gain needs a before/after pilot.
No payload -> units are loads/truck-hours, not tonnes.
"""
import pandas as pd, numpy as np, json, sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))          # analysis/
_ROOT = os.path.dirname(_HERE)                              # repo root
CYCLES_CSV = os.path.join(_ROOT, 'data', 'cycles_all_months.csv')

QUEUE_CAP_MIN = 120     # dwell: queue vs standing idle
PARK_CAP_MIN  = 360     # dwell: on-shift idle (6h) vs off-shift/parked downtime
                        # NOTE both are provisional, BN-tuned constants -> make cycle-relative when generalising

# ---- per-zone config (only what can't be derived from data) --------------------
ZONES = {
    25559: dict(name='BN load (Баруун наран /Зүүн/)', region='bn',  haul_km=34),
    25385: dict(name='Middling load',                  region='other', haul_km=0.4),
    25384: dict(name='Reject load',                    region='other', haul_km=2.0),
}

# ---- lever library: cause bucket / constraint -> recommendation ----------------
# Rule-based lookup (§7). Each lever is a POINTER to a known lever, with mechanism,
# a literature anchor, and an honesty caveat. NOT a validated prescription.
LEVERS = {
    'smooth_queue': dict(
        lever='Smooth arrivals + cut the load queue (dispatch / headway control)',
        mechanism='de-bunch convoys so trucks meet the shovel evenly, cutting the wait at the loader',
        anchor='truck-shovel dispatch & queueing theory (bunching wastes shovel capacity)',
        caveat='within the current fleet availability; no capex.'),
    'road': dict(
        lever='Haul-road improvement (empty return + loaded haul; surface/grade/width at terminals)',
        mechanism='raise haul speed toward free-flow; the delay is concentrated at the two '
                  'terminals, the open road is already efficient',
        anchor='haul-road rolling / grade resistance vs truck productivity',
        caveat='helps only where the haul is long (BN, not Middling); capped by the shovel ceiling.'),
    'staffing': dict(
        lever='Run more productive truck-hours (add/extend shifts, more available trucks)',
        mechanism='the fleet is parked/off-shift a large share of the month; more productive '
                  'truck-hours raise output toward the shovel ceiling',
        anchor='fleet availability / utilisation (theory of constraints — feed the constraint)',
        caveat='a scheduling & staffing decision, NOT dispatch tuning; some standstill is '
               'legitimate (maintenance, rest, blasting).'),
    'dump': dict(
        lever='Dump-side spotting / extra dump position / pile management',
        mechanism='cut dwell at the unload zone (spotting, congestion at the pile)',
        anchor='dump/spotting time in cycle-time studies',
        caveat='only binding where dump excess is large (e.g. Middling), not BN.'),
    'shovel': dict(
        lever='Expand loading capacity (2nd loading position / faster load / bigger bucket)',
        mechanism='raise the shovel service rate = raise the throughput ceiling',
        anchor='theory of constraints — elevate the binding constraint',
        caveat='capex; only pays ABOVE the current shovel ceiling.'),
}


# ================================================================ L1 perception
def perception(zone_id, month):
    C = pd.read_csv(CYCLES_CSV, parse_dates=['depart_load','arrive_unload',
                                             'depart_unload','arrive_load'])
    z = ZONES[zone_id]
    cyc = C[(C['region']==z['region']) & (C['month']==month) &
            (C['load_zone']==zone_id)].copy()
    cyc = cyc.sort_values(['tracker_id','depart_load']).reset_index(drop=True)
    # loading dwell = next depart_load - this arrive_load (same truck, consecutive)
    cyc['next_dl'] = cyc.groupby('tracker_id')['depart_load'].shift(-1)
    same = cyc['tracker_id'].eq(cyc['tracker_id'].shift(-1))
    cyc['load_dwell_s'] = np.where(same,
                                   (cyc['next_dl']-cyc['arrive_load']).dt.total_seconds(),
                                   np.nan)
    cyc.loc[cyc['load_dwell_s']<=0, 'load_dwell_s'] = np.nan
    unload_zone = int(cyc['unload_zone'].mode().iloc[0])
    return cyc, unload_zone


# ================================================================ L2 attribution
def attribution(cyc, dump_cyc):
    """Recoverable truck-hours per cause bucket (cycle-level excess over baselines).
    The loading dwell is split at QUEUE_CAP and PARK_CAP (see module docstring);
    `downtime` (>PARK_CAP) is returned SEPARATELY — it is fleet off-shift time, not
    dispatch-recoverable."""
    d = cyc['load_dwell_s'].dropna()
    svc_load  = d.quantile(.20)                       # no-queue loading service time
    ff_haul   = cyc['haul_s'].quantile(.15)           # free-flow loaded haul
    ff_return = cyc['return_s'].quantile(.15)         # free-flow empty return
    svc_dump  = dump_cyc['dump_s'].quantile(.20)
    qcap, pcap = QUEUE_CAP_MIN*60, PARK_CAP_MIN*60

    h = lambda s: float(np.maximum(0, s).sum())/3600.0
    buckets = {                                                    # recoverable-ish
        'load_queue':   h(d.clip(upper=qcap) - svc_load),         # svc..120min  (queue at shovel)
        'idle_onshift': h(d.clip(upper=pcap) - qcap),             # 120min..6h   (on-shift idle)
        'haul_road':    h(cyc['haul_s'] - ff_haul),               # loaded-haul excess
        'return_road':  h(cyc['return_s'] - ff_return),           # empty-return excess
        'dump':         h(dump_cyc['dump_s'] - svc_dump),         # dump excess
    }
    downtime = h(d - pcap)                                        # >6h/overnight — NOT recoverable
    baselines = dict(svc_load_min=svc_load/60, ff_haul_min=ff_haul/60,
                     ff_return_min=ff_return/60, svc_dump_min=svc_dump/60,
                     queue_cap_min=QUEUE_CAP_MIN, park_cap_min=PARK_CAP_MIN)
    return buckets, downtime, baselines


# ================================================================ L3a capacity
def capacity(cyc, dump_cyc, unload_zone):
    days   = cyc['date'].nunique()
    trucks = cyc['tracker_id'].nunique()
    ncyc   = len(cyc)
    loads_day = ncyc/days

    # effective loading service rate = departure rate while shovel actively working
    dep  = cyc['depart_load'].sort_values()
    gaps = dep.diff().dt.total_seconds().dropna()/60
    busy = gaps[gaps < 30]
    service_rate = 60/busy.median()                              # loads/h when busy

    # productive operating hours/day = hours-of-day carrying >=40% of mean hourly loads
    per_hod = cyc.groupby(cyc['depart_load'].dt.hour).size()
    op_hours = int((per_hod >= 0.4*per_hod.mean()).sum())
    C_load = service_rate * op_hours                            # shovel ceiling, loads/day

    avg_rate = loads_day/op_hours
    util = avg_rate/service_rate                                # shovel busy fraction
    best_day = int(cyc.groupby(cyc['depart_load'].dt.date).size().max())

    # dump-side capacity (is the unload zone binding?)
    ddep = dump_cyc.groupby([dump_cyc['depart_unload'].dt.date,
                             dump_cyc['depart_unload'].dt.hour]).size()
    dump_rate = float(ddep.quantile(.9))

    return dict(days=days, trucks=trucks, ncyc=ncyc, loads_day=loads_day,
                service_rate=service_rate, op_hours=op_hours, C_load=C_load,
                util=util, best_day=best_day, dump_rate=dump_rate, unload_zone=unload_zone)


# ================================================================ L3b decision
def decide(cyc, buckets, downtime_h, cap):
    """Binding constraint + REALISTIC what-if ceilings.
    Realistic = keep the ACTUAL fleet availability; credit only faster ACTIVE cycling
    (remove queue + road waste). Running more truck-hours (cutting downtime) is a SEPARATE
    lever whose ceiling is the shovel."""
    C = cap['C_load']; cur = cap['loads_day']
    d = cyc['load_dwell_s'].dropna()
    svc_load = d.quantile(.20)
    mean_cycle = (cyc['cycle_s'].mean() + d.clip(upper=QUEUE_CAP_MIN*60).mean())/60   # productive cycle
    ret, haul = cyc['return_s'], cyc['haul_s']
    road_save  = float((ret.mean()-ret.quantile(.15) + haul.mean()-haul.quantile(.15))/60)
    queue_save = float(np.maximum(0, d.clip(upper=QUEUE_CAP_MIN*60)-svc_load).mean()/60)

    # same active-time budget, faster cycle -> more cycles; capped by the shovel
    scaled = lambda nc: min(cur*mean_cycle/max(nc, 1.0), C)
    B_road   = scaled(mean_cycle - road_save)                    # fix roads only
    B_active = scaled(mean_cycle - road_save - queue_save)       # + cut load queue

    shovel_bound = cap['util'] >= 0.85                           # shovel already near-saturated?
    binding_now = ('shovel (loading)' if shovel_bound
                   else 'low fleet utilisation + active-cycle waste (queue / road)')
    road_helps = B_road > cur + 1
    return dict(mean_cycle_min=mean_cycle, road_save_min=road_save, queue_save_min=queue_save,
                ceiling_active=B_active, ceiling_road=B_road, shovel_ceiling=C,
                downtime_h=downtime_h, binding_now=binding_now, road_helps=road_helps,
                util=cap['util'])


# ================================================================ L3c recommend
def recommend(buckets, downtime_h, cap, dec):
    cur = cap['loads_day']; C = cap['C_load']
    B_active, B_road = dec['ceiling_active'], dec['ceiling_road']
    pct = lambda x: 100*(x-cur)/cur
    recs = []
    # 1 — smooth arrivals / cut the load queue (within current availability)
    recs.append(dict(rank=1, key='smooth_queue', **LEVERS['smooth_queue'],
        recoverable_truck_h=round(buckets['load_queue']),
        throughput_effect=f"part of the active-cycle ceiling {cur:.0f} -> {B_active:.0f} loads/day (+{pct(B_active):.0f}%)",
        prereq='none', note='within current fleet availability; no capex'))
    # 2 — road (helps only where the haul is long)
    road_eff = (f"road-only ~{B_road:.0f}/day; with the queue -> {B_active:.0f}/day"
                if dec['road_helps'] else "~0 — the haul is short here, road is not the issue")
    recs.append(dict(rank=2, key='road', **LEVERS['road'],
        recoverable_truck_h=round(buckets['return_road']+buckets['haul_road']),
        throughput_effect=road_eff, prereq='none',
        note='within current fleet availability; capped by shovel ceiling'))
    # 3 — staffing: address downtime -> up to the shovel ceiling (SEPARATE lever)
    recs.append(dict(rank=3, key='staffing', **LEVERS['staffing'],
        recoverable_truck_h=round(downtime_h),
        throughput_effect=f"{B_active:.0f} -> up to the shovel ceiling {C:.0f}/day (staffing/scheduling, not dispatch)",
        prereq='separate operational decision',
        note=f'~{round(downtime_h)} truck-h/mo parked/off-shift; some is legitimate (maintenance/rest)'))
    # 4 — shovel: only above the ceiling
    recs.append(dict(rank=4, key='shovel', **LEVERS['shovel'],
        recoverable_truck_h=None,
        throughput_effect=f"raises the ceiling above {C:.0f}/day",
        prereq=f'only after throughput reaches the shovel ceiling {C:.0f}',
        note='capex; last'))
    # dump lever if the dump bucket is materially large (e.g. Middling)
    if buckets['dump'] > 0.15*sum(buckets.values()):
        recs.insert(1, dict(rank=2, key='dump', **LEVERS['dump'],
            recoverable_truck_h=round(buckets['dump']),
            throughput_effect="material — dump excess is large for this flow",
            prereq='none', note='dump zone is a real bottleneck here'))
        for i, r in enumerate(recs): r['rank'] = i+1
    return recs


# ================================================================ orchestrator
def diagnose(zone_id, month='2025-11'):
    z = ZONES[zone_id]
    cyc, unload_zone = perception(zone_id, month)
    dump_cyc = cyc[cyc['unload_zone']==unload_zone].copy()
    buckets, downtime_h, baselines = attribution(cyc, dump_cyc)
    cap = capacity(cyc, dump_cyc, unload_zone)
    dec = decide(cyc, buckets, downtime_h, cap)
    recs = recommend(buckets, downtime_h, cap, dec)
    total_h = sum(buckets.values())
    return dict(
        zone_id=zone_id, name=z['name'], region=z['region'], month=month,
        unload_zone=unload_zone, haul_km=z['haul_km'],
        throughput=dict(loads_day=round(cap['loads_day'],1),
                        cycles_per_truck_day=round(cap['loads_day']/cap['trucks'],2),
                        trucks=cap['trucks'], days=cap['days'], best_day=cap['best_day']),
        cycle=dict(full_cycle_min=round(dec['mean_cycle_min'],1),
                   **{k:round(v,1) for k,v in baselines.items()}),
        capacity=dict(service_rate_load=round(cap['service_rate'],1),
                      op_hours=cap['op_hours'], shovel_ceiling=round(cap['C_load']),
                      utilisation=round(cap['util'],2), dump_rate_p90=round(cap['dump_rate'],1)),
        attribution=dict(recoverable_truck_h={k:round(v) for k,v in buckets.items()},
                         total_truck_h=round(total_h),
                         share_pct={k:round(100*v/total_h) for k,v in buckets.items()},
                         downtime_truck_h=round(downtime_h)),
        decision=dict(binding_now=dec['binding_now'], road_helps=bool(dec['road_helps']),
                      ceiling_active=round(dec['ceiling_active']),
                      ceiling_road=round(dec['ceiling_road']),
                      shovel_ceiling=round(dec['shovel_ceiling']),
                      downtime_truck_h=round(downtime_h)),
        recommendations=recs,
        caveats=['Nov-only', 'cycle-level free-flow baselines (p15/p20)',
                 'recoverable hours = UPPER BOUND',
                 'idle split at PARK_CAP=6h is a provisional, BN-tuned threshold (make cycle-relative when generalising)',
                 'realistic ceiling assumes current fleet availability + constant service rate',
                 'downtime = fleet off-shift/parked, addressed by staffing not dispatch',
                 'no payload -> units are loads/truck-hours', 'DIAGNOSTIC not proof — needs before/after pilot'])


# ================================================================ pretty printer
def report(dx):
    L=[]; p=L.append
    p("="*74)
    p(f"DIAGNOSIS — {dx['name']}  (zone {dx['zone_id']}, {dx['month']})")
    p("="*74)
    t=dx['throughput']
    p(f"THROUGHPUT : {t['loads_day']} loads/day  |  {t['trucks']} trucks x {t['cycles_per_truck_day']} cyc  |  best day {t['best_day']}")
    c=dx['capacity']
    p(f"CAPACITY   : shovel {c['service_rate_load']} loads/h x {c['op_hours']}h = ceiling {c['shovel_ceiling']}/day  |  utilisation {c['utilisation']*100:.0f}%  |  dump p90 {c['dump_rate_p90']}/h")
    cy=dx['cycle']
    p(f"CYCLE      : {cy['full_cycle_min']} min (load svc {cy['svc_load_min']:.0f} · ff-haul {cy['ff_haul_min']:.0f} · ff-return {cy['ff_return_min']:.0f})")
    a=dx['attribution']
    p(f"\nRECOVERABLE LOST TIME (truck-h/month, UPPER BOUND, total {a['total_truck_h']}):")
    for k,v in sorted(a['recoverable_truck_h'].items(), key=lambda x:-x[1]):
        p(f"   {k:13s} {v:6d} h  ({a['share_pct'][k]:2d}%)")
    p(f"   {'-'*54}")
    p(f"   downtime      {a['downtime_truck_h']:6d} h   (>6h/overnight — fleet off-shift; STAFFING lever, not dispatch-recoverable)")
    d=dx['decision']
    p(f"\nCONSTRAINT : binding NOW = {d['binding_now'].upper()}")
    p(f"             cut queue+road (current fleet)          {t['loads_day']:.0f} -> {d['ceiling_active']}/day")
    p(f"             + run more truck-hours (cut downtime)   -> up to shovel ceiling {d['shovel_ceiling']}/day")
    p(f"\nRECOMMENDATIONS (prioritised pointers, not validated prescriptions):")
    for r in dx['recommendations']:
        p(f"  #{r['rank']}  {r['lever']}")
        p(f"       why   : {r['mechanism']}")
        p(f"       effect: {r.get('throughput_effect','')}")
        if r.get('recoverable_truck_h'): p(f"       recoverable: ~{r['recoverable_truck_h']} truck-h/mo   prereq: {r['prereq']}")
        p(f"       lit   : {r['anchor']}")
        p(f"       caveat: {r['caveat']}")
    p("="*74)
    return "\n".join(L)


if __name__ == '__main__':
    zid = int(sys.argv[1]) if len(sys.argv)>1 else 25559
    dx = diagnose(zid)
    print(report(dx))
    out = os.path.join(_HERE, f"diagnosis_{zid}.json")
    json.dump(dx, open(out,'w'), indent=2, ensure_ascii=False)
    print(f"\n[structured diagnosis -> {out}  (this is the LLM layer's input)]")
