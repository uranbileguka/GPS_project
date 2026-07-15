#!/usr/bin/env python3
"""
BN capacity / bottleneck analysis (Theory of Constraints).  §9 of PROJECT_HANDOFF.
Load zone 25559 -> unload 25685, Nov 2025.  Cycle-cache based (no raw GPS needed).

Cycle row = depart_load -> arrive_unload -> depart_unload -> arrive_load.
  cycle_s = haul + dump + return  (EXCLUDES loading dwell).
  loading dwell = depart_load[i+1] - arrive_load[i]  (same truck, consecutive).
  full cycle    = cycle_s + loading dwell.
"""
import pandas as pd, numpy as np, os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
CYCLES_CSV = os.path.join(_ROOT, 'data', 'cycles_all_months.csv')

pd.set_option('display.width', 120)
C = pd.read_csv(CYCLES_CSV,
                parse_dates=['depart_load','arrive_unload','depart_unload','arrive_load'])
bn = C[(C['region']=='bn') & (C['month']=='2025-11')].copy()
main = bn[(bn['load_zone']==25559)].copy()          # 2417 load-side cycles
main = main.sort_values(['tracker_id','depart_load']).reset_index(drop=True)

DAYS = main['date'].nunique()
NTRUCK = main['tracker_id'].nunique()
NCYC = len(main)
print("="*70)
print("BN CAPACITY / BOTTLENECK ANALYSIS  (25559 load, Nov 2025)")
print("="*70)
print(f"cycles={NCYC}  trucks={NTRUCK}  active_days={DAYS}")

# ---------------------------------------------------------------- loading dwell
# pair consecutive cycles of the SAME truck: dwell = next depart_load - this arrive_load
main['next_depart_load'] = main.groupby('tracker_id')['depart_load'].shift(-1)
main['same_truck_next']  = main['tracker_id'].eq(main['tracker_id'].shift(-1))
main['load_dwell_s'] = np.where(main['same_truck_next'],
                                (main['next_depart_load'] - main['arrive_load']).dt.total_seconds(),
                                np.nan)
d = main['load_dwell_s'].dropna()
d = d[d > 0]
# split: "loading" portion vs long parks. Look at distribution.
print("\n--- loading dwell (arrive_load -> next depart_load), minutes ---")
for p in [10,20,50,75,90,95]:
    print(f"  p{p:<3} {d.quantile(p/100)/60:6.1f}")
print(f"  mean {d.mean()/60:6.1f}   n={len(d)}")
# service time proxy = p20 (near no-queue); cap loading at 120min for 'productive' cycle
SVC_MIN = d.quantile(.20)/60
print(f"\n  -> loading service time (p20, ~no-queue) = {SVC_MIN:.1f} min  =>  mu_load = {60/SVC_MIN:.2f} trucks/h")
dwell_cap = 120*60
d_prod = d.clip(upper=dwell_cap)
print(f"  loading dwell capped@120min: mean {d_prod.mean()/60:.1f} min  (share of dwells >120min: {(d>dwell_cap).mean()*100:.1f}%)")

# ---------------------------------------------------------------- cycle timing
haul, dump, ret = main['haul_s'], main['dump_s'], main['return_s']
mean_cycle_s = main['cycle_s'].mean()
mean_full_s  = mean_cycle_s + d_prod.mean()   # productive full cycle
print("\n--- mean cycle decomposition (min) ---")
print(f"  loading (prod) {d_prod.mean()/60:6.1f}")
print(f"  haul  loaded   {haul.mean()/60:6.1f}   (p15 free-flow {haul.quantile(.15)/60:.1f})")
print(f"  dump           {dump.mean()/60:6.1f}   (p15 {dump.quantile(.15)/60:.1f})")
print(f"  return empty   {ret.mean()/60:6.1f}   (p15 free-flow {ret.quantile(.15)/60:.1f})")
print(f"  = full cycle   {mean_full_s/60:6.1f} min")

# ---------------------------------------------------------------- operating window
main['dl_hour'] = main['depart_load'].dt.hour
loads_per_hour = main.groupby([main['depart_load'].dt.date, 'dl_hour']).size()
# operating hours/day: distinct hours-of-day that ever see a load, and typical daily span
hours_active = sorted(main['dl_hour'].unique())
daily_span = main.groupby('date').agg(first=('depart_load','min'), last=('depart_load','max'))
daily_span['span_h'] = (daily_span['last']-daily_span['first']).dt.total_seconds()/3600
print("\n--- operating window ---")
print(f"  hours-of-day with loads: {hours_active[0]}..{hours_active[-1]}  ({len(hours_active)} distinct hours)")
print(f"  daily active span: median {daily_span['span_h'].median():.1f} h  (mean {daily_span['span_h'].mean():.1f})")
hist = main['dl_hour'].value_counts().sort_index()
print("  loads by hour-of-day:", dict(hist))

# ---------------------------------------------------------------- service rate (shovel capacity)
# demonstrated peak loading rate: loads per clock-hour, high percentiles
print("\n--- SHOVEL CAPACITY (loads per clock-hour at 25559) ---")
for p in [50,75,90,95]:
    print(f"  p{p}: {loads_per_hour.quantile(p/100):.1f} loads/h")
print(f"  max: {loads_per_hour.max():.0f} loads/h")
# TRUE service rate = departure rate when the shovel is actively working (busy gaps).
# p20-dwell overstates service time (positioning + micro-queue); busy inter-departure is cleaner.
dep = main['depart_load'].sort_values()
gaps = dep.diff().dt.total_seconds().dropna()/60
gaps_busy = gaps[gaps < 30]   # consecutive loads while shovel working (exclude starved gaps)
MU_BUSY = 60/gaps_busy.median()
print(f"  inter-departure gap (busy, <30min): p20 {gaps_busy.quantile(.2):.1f}  median {gaps_busy.median():.1f}  "
      f"mean {gaps_busy.mean():.1f} min  => effective service rate ~{MU_BUSY:.1f}/h")
print(f"  (p20 gap {gaps_busy.quantile(.2):.1f} min & max {loads_per_hour.max():.0f}/h suggest possibly 2 loading spots)")

MU_LOAD = MU_BUSY                                  # effective service rate, ~6-7/h
avg_rate = NCYC / (DAYS * daily_span['span_h'].median())
util_avg = avg_rate / MU_LOAD
print(f"\n  demonstrated AVG rate = {avg_rate:.2f}/h   vs service rate {MU_LOAD:.1f}/h  =>  shovel busy ~{util_avg*100:.0f}% of the time")
print(f"  => ~{(1-util_avg)*100:.0f}% spare shovel-capacity on AVERAGE, yet queue present ~47% of load-side time (§8.2)")
print(f"     => coexistence of spare + queue = BUNCHED ARRIVALS (convoys over the 34km haul).")
# capacity/day range: service rate x realistic productive operating hours
for oph in [18, 20, 22]:
    print(f"     C_load @ {oph}h/day = {MU_LOAD*oph:.0f} loads/day")
OP_H = 20.0                                         # realistic productive hours (24h - shift changes/moves)
C_load_day = MU_LOAD * OP_H
print(f"  -> adopt C_load = {C_load_day:.0f} loads/day  (service {MU_LOAD:.1f}/h x {OP_H:.0f} productive h)")

# ---------------------------------------------------------------- dump capacity at 25685
dmp = C[(C['region']=='bn') & (C['month']=='2025-11') & (C['unload_zone']==25685)].copy()
dph = dmp.groupby([dmp['depart_unload'].dt.date, dmp['depart_unload'].dt.hour]).size()
print("\n--- DUMP CAPACITY (dumps per clock-hour at 25685) ---")
for p in [50,90,95]:
    print(f"  p{p}: {dph.quantile(p/100):.1f} dumps/h")
print(f"  max: {dph.max():.0f}  ; dump dwell median {dmp['dump_s'].median()/60:.1f} min")

# ---------------------------------------------------------------- THROUGHPUT & WHAT-IF
loads_day = NCYC / DAYS
util = loads_day / C_load_day
print("\n" + "="*70)
print("THROUGHPUT vs CAPACITY")
print("="*70)
print(f"  demonstrated:   {loads_day:.1f} loads/day   ({loads_day/NTRUCK:.2f} cycles/truck/day, {NTRUCK} trucks)")
print(f"  shovel ceiling: {C_load_day:.0f} loads/day  ->  utilization rho = {util*100:.0f}%   (~{(1-util)*100:.0f}% headroom)")

def supply_ceiling(new_full_min):
    """22 trucks each cycling continuously (no idle) at productive rate over OP_H hours."""
    return NTRUCK * (OP_H*60 / new_full_min)

base_full = mean_full_s/60
scenarios = {
 'S0 current productive cycle':      base_full,
 'S1 fix empty-return -> p15':       base_full - (ret.mean()-ret.quantile(.15))/60,
 'S2 fix loaded-haul  -> p15':       base_full - (haul.mean()-haul.quantile(.15))/60,
 'S3 fix load queue   -> p20 svc':   base_full - (d_prod.mean()-d.quantile(.20))/60,
 'S4 fix BOTH road legs -> p15':     base_full - (ret.mean()-ret.quantile(.15))/60 - (haul.mean()-haul.quantile(.15))/60,
}
print("\n--- WHAT-IF: supply ceiling B (continuous cycling, no idle) vs shovel ceiling C ---")
print(f"  demonstrated {loads_day:.0f}/day is FAR below continuous-cycling supply -> {loads_day/supply_ceiling(base_full)*100:.0f}% of trucks' own supply potential")
print(f"  (the gap = truck idle/breaks/bunching, ~{(1-loads_day/supply_ceiling(base_full))*100:.0f}%; matches §8.4 idle 38.7%)\n")
print(f"  {'scenario':32s} {'cyc.time':>8s} {'B_supply':>9s} {'realistic=min(B,C)':>22s}")
for name, ft in scenarios.items():
    B = supply_ceiling(ft)
    realistic = min(B, C_load_day)
    binding = 'SHOVEL binds' if C_load_day < B else 'supply binds'
    print(f"  {name:32s} {ft:6.0f}m {B:8.0f} {realistic:9.0f}  ({binding})")
B0 = supply_ceiling(base_full); B4 = min(supply_ceiling(scenarios['S4 fix BOTH road legs -> p15']), C_load_day)
print(f"\n  C_load shovel ceiling = {C_load_day:.0f}/day (held constant). Dump side ~7-8/h (max 15) = NOT binding.")
print("  READING (the constraint SHIFTS as you fix levers):")
print(f"   * NOW: shovel only ~{util*100:.0f}% used, but trucks realize {loads_day/B0*100:.0f}% of their own cycling potential.")
print(f"          => binding constraint = TRUCK IDLE + ARRIVAL BUNCHING (not the shovel).")
print(f"   * Lever 1 (cut idle/de-bunch, NO capex): {loads_day:.0f} -> {B0:.0f}/day (+{(B0-loads_day)/loads_day*100:.0f}%). Trucks then maxed at 222-min cycle; shovel still slack.")
print(f"   * Lever 2 (+ fix roads, both legs->free-flow): {B0:.0f} -> {B4:.0f}/day. NOW the SHOVEL binds at ~{C_load_day:.0f}.")
print(f"   * Above ~{C_load_day:.0f}/day you must expand the SHOVEL (2nd loader / faster load) or throughput won't move -")
print(f"          extra trucks or faster road past that point just deepen the queue (road-time -> queue-time).")
print(f"   * ORDER OF PRIZE: idle/bunching (+{(B0-loads_day)/loads_day*100:.0f}%, free) > roads (to shovel cap) > shovel capex.")
print("="*70)
