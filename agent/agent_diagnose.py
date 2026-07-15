#!/usr/bin/env python3
"""
Diagnostic agent core  —  diagnose(zone_id, month) -> structured diagnosis dict.

Integrates the four-layer framework (PROJECT_HANDOFF §7), everything BEFORE the LLM:
    L1 perception    -> cycles + cycle decomposition + loading dwell   (perception)
    L2 attribution   -> recoverable truck-hours per cause bucket       (attribution)
    L3a capacity     -> service rate, utilisation, bunching, ceiling   (capacity, ToC §9)
    L3b decision     -> binding constraint now + after each lever       (decide)
    L3c recommend    -> constraint/bucket -> literature-backed lever    (recommend)
The returned dict is what the (future) L4 LLM layer will narrate.

Self-contained on data/cycles_all_months.csv.  Generalises across load zones
(config-driven) so the SAME code diagnoses BN and Middling differently.

Honesty frame (§7): this is a DIAGNOSTIC, not an optimiser. Recoverable hours are
UPPER BOUNDS; "throughput effect" is a what-if ceiling, not a proven gain — proving
a gain needs a before/after pilot. No payload -> units are loads/truck-hours, not tonnes.
"""
import pandas as pd, numpy as np, json, sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))          # analysis/
_ROOT = os.path.dirname(_HERE)                              # repo root
CYCLES_CSV = os.path.join(_ROOT, 'data', 'cycles_all_months.csv')

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
    'idle_bunching': dict(
        lever='Smooth arrivals + cut standing time (dispatch / headway control)',
        mechanism='de-bunch convoys so trucks meet the shovel evenly; overlap shift '
                  'changes; in-field refuel; reduce inter-cycle parking',
        anchor='truck-shovel dispatch & queueing theory (bunching wastes shovel capacity)',
        caveat='needs no capex, but assumes standing time is genuinely recoverable '
               '(some is legit breaks/maintenance).'),
    'return_road': dict(
        lever='Empty-return road improvement (surface/grade/width, speed at terminals)',
        mechanism='raise empty-haul speed toward free-flow; delay concentrated at '
                  'the two terminals, open road is already efficient',
        anchor='haul-road rolling resistance / road resistance vs truck productivity',
        caveat='only lifts throughput AFTER trucks are cycle-bound, and only up to '
               'the shovel ceiling.'),
    'haul_road': dict(
        lever='Loaded-haul road improvement (grade/surface at load-end)',
        mechanism='raise loaded-haul speed toward free-flow',
        anchor='haul-road rolling resistance / grade resistance',
        caveat='load-end road delay overlaps the load queue — do not double-count; '
               'capped by shovel ceiling.'),
    'dump': dict(
        lever='Dump-side spotting / extra dump position / pile management',
        mechanism='cut dwell at the unload zone (spotting, congestion at the pile)',
        anchor='dump/spotting time in cycle-time studies',
        caveat='only binding where dump excess is large (e.g. Middling), not BN.'),
    'shovel': dict(
        lever='Expand loading capacity (2nd loading position / faster load / bigger bucket)',
        mechanism='raise the shovel service rate = raise the throughput ceiling',
        anchor='theory of constraints — elevate the binding constraint',
        caveat='capex; only pays ABOVE the current shovel ceiling, i.e. after idle '
               'and road are already fixed.'),
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
    """Recoverable truck-hours per cause bucket (cycle-level excess over baselines)."""
    d = cyc['load_dwell_s'].dropna()
    svc_load  = d.quantile(.20)                       # no-queue loading service time
    ff_haul   = cyc['haul_s'].quantile(.15)           # free-flow loaded haul
    ff_return = cyc['return_s'].quantile(.15)         # free-flow empty return
    svc_dump  = dump_cyc['dump_s'].quantile(.20)
    LOAD_CAP  = 120*60                                # split loading-queue vs standing

    dcap = d.clip(upper=LOAD_CAP)
    h = lambda s: float(np.maximum(0, s).sum())/3600.0
    buckets = {
        'load_queue':  h(dcap - svc_load),                         # queue within loading
        'idle_stand':  h(d - LOAD_CAP),                            # inter-cycle standing (upper bnd)
        'haul_road':   h(cyc['haul_s'] - ff_haul),                 # loaded-haul excess
        'return_road': h(cyc['return_s'] - ff_return),             # empty-return excess
        'dump':        h(dump_cyc['dump_s'] - svc_dump),           # dump excess
    }
    baselines = dict(svc_load_min=svc_load/60, ff_haul_min=ff_haul/60,
                     ff_return_min=ff_return/60, svc_dump_min=svc_dump/60)
    return buckets, baselines


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
    hourly = cyc.groupby([cyc['depart_load'].dt.date, cyc['depart_load'].dt.hour]).size()
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
                util=util, best_day=best_day, dump_rate=dump_rate,
                unload_zone=unload_zone)


# ================================================================ L3b decision
def decide(cyc, buckets, cap):
    """Binding constraint now + what-if ceilings (ToC). Every ceiling capped by the shovel."""
    trucks, op_h, C = cap['trucks'], cap['op_hours'], cap['C_load']
    # productive full cycle (loading capped at 120min so parking doesn't inflate)
    d = cyc['load_dwell_s'].dropna().clip(upper=120*60)
    full_min = (cyc['cycle_s'].mean() + d.mean())/60
    ret, haul = cyc['return_s'], cyc['haul_s']
    ff_ret  = (ret.mean()-ret.quantile(.15))/60
    ff_haul = (haul.mean()-haul.quantile(.15))/60

    supply = lambda fmin: trucks*(op_h*60/fmin)                # continuous-cycling supply
    B0_raw = supply(full_min)                                  # cut idle only (same cycle), UNCAPPED
    B0     = min(B0_raw, C)                                    # ... capped by shovel
    B_road = min(supply(full_min-ff_ret-ff_haul), C)          # + fix both road legs, capped

    cur = cap['loads_day']
    # what binds TODAY: idle if demonstrated is well below both the trucks' own supply and the shovel
    idle_bound = cur < 0.9*B0_raw and cur < 0.9*C
    binding_now = 'truck idle + arrival bunching' if idle_bound else \
                  ('shovel (loading)' if B0_raw >= C else 'truck cycle time (road)')
    # does the road lever add throughput beyond just cutting idle? only if idle-fix hasn't already hit the shovel
    road_helps = (B0 < C-1) and (B_road > B0+1)
    shifts_to  = 'shovel (loading)' if B0 >= C-1 or B_road >= C-1 else 'truck cycle time (road)'
    return dict(full_cycle_min=full_min, supply_cut_idle=B0, supply_cut_idle_raw=B0_raw,
                ceiling_with_road=B_road, shovel_ceiling=C, binding_now=binding_now,
                road_saving_min=ff_ret+ff_haul, road_helps=road_helps, shifts_to=shifts_to)


# ================================================================ L3c recommend
def recommend(buckets, cap, dec):
    cur = cap['loads_day']; C = cap['C_load']
    B0  = dec['supply_cut_idle']; B_road = dec['ceiling_with_road']
    def pct(x): return 100*(x-cur)/cur
    recs = []
    # 1 — idle/bunching: the active constraint, throughput NOW
    recs.append(dict(rank=1, key='idle_bunching', **LEVERS['idle_bunching'],
        recoverable_truck_h=round(buckets['load_queue']+buckets['idle_stand']),
        throughput_now=f"{cur:.0f} -> {min(B0,C):.0f} loads/day (+{pct(min(B0,C)):.0f}%)",
        prereq='none', note='binding constraint NOW; free (no capex)'))
    # 2 — road: only pays after idle fixed, capped by shovel
    road_after = (f"{B0:.0f} -> {B_road:.0f} loads/day" if dec['road_helps']
                  else f"no throughput gain — shovel already binds at {C:.0f}/day (still cuts fuel/wear)")
    recs.append(dict(rank=2, key='return_road', **LEVERS['return_road'],
        recoverable_truck_h=round(buckets['return_road']+buckets['haul_road']),
        throughput_now="~0 while idle-bound",
        throughput_after_prereq=road_after,
        prereq='fix idle/bunching first', note='shortens cycle; capped by shovel ceiling'))
    # 3 — shovel: elevate the ceiling, only above current cap
    recs.append(dict(rank=3, key='shovel', **LEVERS['shovel'],
        recoverable_truck_h=None,
        throughput_now="0 (shovel has spare now)",
        throughput_after_prereq=f"raises ceiling above {C:.0f}/day",
        prereq='only after idle+road push throughput to the shovel ceiling',
        note='capex; last, not first'))
    # dump lever only if dump bucket is materially large
    if buckets['dump'] > 0.15*sum(v for k,v in buckets.items()):
        recs.insert(2, dict(rank=2, key='dump', **LEVERS['dump'],
            recoverable_truck_h=round(buckets['dump']),
            throughput_now="material — dump excess is large here",
            prereq='none', note='dump zone is a real bottleneck for this flow'))
        for i,r in enumerate(recs): r['rank']=i+1
    return recs


# ================================================================ orchestrator
def diagnose(zone_id, month='2025-11'):
    z = ZONES[zone_id]
    cyc, unload_zone = perception(zone_id, month)
    dump_cyc = cyc[cyc['unload_zone']==unload_zone].copy()
    buckets, baselines = attribution(cyc, dump_cyc)
    cap = capacity(cyc, dump_cyc, unload_zone)
    dec = decide(cyc, buckets, cap)
    recs = recommend(buckets, cap, dec)
    total_h = sum(buckets.values())
    return dict(
        zone_id=zone_id, name=z['name'], region=z['region'], month=month,
        unload_zone=unload_zone, haul_km=z['haul_km'],
        throughput=dict(loads_day=round(cap['loads_day'],1),
                        cycles_per_truck_day=round(cap['loads_day']/cap['trucks'],2),
                        trucks=cap['trucks'], days=cap['days'], best_day=cap['best_day']),
        cycle=dict(full_cycle_min=round(dec['full_cycle_min'],1), **{k:round(v,1) for k,v in baselines.items()}),
        capacity=dict(service_rate_load=round(cap['service_rate'],1),
                      op_hours=cap['op_hours'], shovel_ceiling=round(cap['C_load']),
                      utilisation=round(cap['util'],2), dump_rate_p90=round(cap['dump_rate'],1)),
        attribution=dict(recoverable_truck_h={k:round(v) for k,v in buckets.items()},
                         total_truck_h=round(total_h),
                         share_pct={k:round(100*v/total_h) for k,v in buckets.items()}),
        decision=dict(binding_now=dec['binding_now'], shifts_to=dec['shifts_to'],
                      road_helps=bool(dec['road_helps']),
                      supply_cut_idle=round(dec['supply_cut_idle']),
                      ceiling_with_road=round(dec['ceiling_with_road']),
                      shovel_ceiling=round(dec['shovel_ceiling'])),
        recommendations=recs,
        caveats=['Nov-only', 'cycle-level free-flow baselines (p15/p20)',
                 'recoverable hours = UPPER BOUND', 'idle_stand includes legit breaks',
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
    p(f"\nLOST TIME (recoverable truck-h/month, UPPER BOUND, total {a['total_truck_h']}):")
    for k,v in sorted(a['recoverable_truck_h'].items(), key=lambda x:-x[1]):
        p(f"   {k:13s} {v:6d} h  ({a['share_pct'][k]:2d}%)")
    d=dx['decision']
    p(f"\nCONSTRAINT : binding NOW = {d['binding_now'].upper()}")
    road_txt = (f"+ fix roads -> {d['ceiling_with_road']}/day" if d['road_helps']
                else f"roads add nothing (shovel already binds at {d['shovel_ceiling']}/day)")
    p(f"             cut idle/de-bunch -> {d['supply_cut_idle']}/day ; {road_txt} ; ceiling = {d['shifts_to']}")
    p(f"\nRECOMMENDATIONS (prioritised pointers, not validated prescriptions):")
    for r in dx['recommendations']:
        p(f"  #{r['rank']}  {r['lever']}")
        p(f"       why   : {r['mechanism']}")
        eff = r.get('throughput_now','')
        if r.get('throughput_after_prereq'): eff += f"  |  after prereq: {r['throughput_after_prereq']}"
        p(f"       effect: {eff}")
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
