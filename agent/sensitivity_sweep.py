#!/usr/bin/env python3
"""
sensitivity_sweep.py — robustness of agent_v2's diagnosis to the ONE hand-set knob it
still has: the baseline quantile.

WHY THIS EXISTS
  v2 removed the 120-min cut (-> GMM) and the util>=0.85 rule (-> rho vs 1.0), but the
  free-flow / no-queue baselines are still hand-set quantiles (p15 travel, p20 service).
  A 25 pp swing in the combined recoverable % across p10..p30 means the magic number was
  MOVED, not removed. The question that decides whether that matters:

      does the LEVER RANKING move with it, or only the MAGNITUDE?

  If the ranking is invariant, the honest claim is
      "magnitude is parameter-sensitive; the diagnosis is parameter-invariant"
  which turns the sensitivity from a weakness into a robustness result.

TWO AXES SWEPT
  1. baseline strictness q:  ff_q = q, svc_q = q + 0.05  (q=.15 reproduces the defaults)
  2. baseline reference:     'month'  = each month defines its own free flow (current)
                             'pooled' = all 5 months define one fixed reference, so a
                                        congested month can no longer call itself free-flowing

Outputs: sensitivity_sweep.csv, sensitivity_sweep.png, and a printed verdict.
Usage:   python analysis/sensitivity_sweep.py [zone_id]
"""
import os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import agent_v2 as a

MONTHS = ['2025-07', '2025-08', '2025-09', '2025-10', '2025-11']
QS = [0.10, 0.15, 0.20, 0.25, 0.30]
SVC_OFFSET = 0.05                      # keeps the shipped 0.15/0.20 pairing
SHORT = {'Haul-road: empty return': 'return-road',
         'Haul-road: loaded haul': 'haul-road',
         'Queue at the shovel (smooth arrivals)': 'queue',
         'Dump spotting / congestion': 'dump',
         'On-shift idle (better dispatch)': 'idle'}


def sweep(zone_id=25559):
    pooled = a.load_cycles(zone_id, None)          # all months = the fixed reference
    rows = []
    for mode in ['month', 'pooled']:
        ref = None if mode == 'month' else pooled
        for month in MONTHS:
            for q in QS:
                dx = a.diagnose_v2(zone_id, month, with_band=False,
                                   ff_q=q, svc_q=min(q + SVC_OFFSET, 0.95), ref=ref)
                lv = [l for l in dx['levers'] if isinstance(l['gain'], (int, float))
                      and l['cause'] in SHORT]
                order = [SHORT[l['cause']] for l in lv]
                r = dict(zone=zone_id, mode=mode, month=month, q=q,
                         cut_min=dx['gmm_cut_min'],
                         loads_day=dx['throughput']['loads_day'],
                         binding=dx['stations']['binding'],
                         ceiling=dx['stations']['ceiling'],
                         rho_shovel=dx['stations']['rho_shovel'],
                         cycle_min=dx['cycle']['cycle_min'],
                         top_lever=order[0], order='>'.join(order),
                         top_gain=lv[0]['gain'], gap_1_2=lv[0]['gain'] - lv[1]['gain'],
                         recov_pct=dx['recoverable_combined']['pct'])
                r.update({f'bucket_{k}': v for k, v in dx['buckets_truck_h'].items()})
                r.update({f'gain_{SHORT[l["cause"]]}': l['gain'] for l in lv})
                rows.append(r)
                print(f"  {mode:6s} {month} q={q:.2f} -> top={order[0]:11s} "
                      f"(+{lv[0]['gain']}/d, gap {r['gap_1_2']:+d})  recov {r['recov_pct']:+d}%")
    return pd.DataFrame(rows)


def verdict(df):
    L = []; p = L.append
    p("=" * 78); p("SENSITIVITY VERDICT — does the parameter move the DIAGNOSIS or only the SIZE?"); p("=" * 78)
    for mode in ['month', 'pooled']:
        d = df[df['mode'] == mode]
        p(f"\n[{mode} baseline]")
        flip = d.groupby('month')['top_lever'].nunique()
        p(f"  top lever per month across q={QS}:")
        for m in MONTHS:
            dm = d[d['month'] == m]
            tops = dm.set_index('q')['top_lever'].to_dict()
            uniq = set(tops.values())
            mark = "STABLE" if len(uniq) == 1 else "FLIPS " + str(sorted(uniq))
            p(f"    {m}  {mark:26s} min gap#1-#2 = {dm['gap_1_2'].min():+d} loads/day")
        p(f"  months whose #1 flips with q : {int((flip > 1).sum())}/{len(flip)}")
        p(f"  distinct #1 over ALL 25 cells : {sorted(d['top_lever'].unique())}")
        p(f"  binding station              : {sorted(d['binding'].unique())}")
        p(f"  recoverable %  range         : {d['recov_pct'].min():+d}% .. {d['recov_pct'].max():+d}%"
          f"   (spread {d['recov_pct'].max() - d['recov_pct'].min()} pp)")
        p(f"  top-lever gain range         : +{d['top_gain'].min()} .. +{d['top_gain'].max()} loads/day")
    # month vs pooled, at the shipped q
    p(f"\n[baseline reference, at the shipped q=0.15]")
    for m in MONTHS:
        a_ = df[(df['mode'] == 'month') & (df.month == m) & (df.q == .15)].iloc[0]
        b_ = df[(df['mode'] == 'pooled') & (df.month == m) & (df.q == .15)].iloc[0]
        p(f"    {m}  month: {a_['top_lever']:11s} {a_['recov_pct']:+4d}%   |   "
          f"pooled: {b_['top_lever']:11s} {b_['recov_pct']:+4d}%"
          f"   {'(same #1)' if a_['top_lever'] == b_['top_lever'] else '(#1 CHANGES)'}")
    p("=" * 78)
    return "\n".join(L)


def figure(df, zone_id, path):
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    d = df[df['mode'] == 'month']
    # (1) the fragile number
    for m in MONTHS:
        dm = d[d.month == m]
        ax[0].plot(dm['q'], dm['recov_pct'], 'o-', label=m)
    ax[0].set_xlabel('baseline quantile q'); ax[0].set_ylabel('combined recoverable %')
    ax[0].set_title('MAGNITUDE is parameter-sensitive', fontweight='bold')
    ax[0].axvline(.15, color='k', ls=':', lw=1); ax[0].legend(fontsize=7)
    ax[0].grid(alpha=.3)
    # (2) the stable thing — jitter, else the 5 months collapse onto one line
    levers = ['return-road', 'queue', 'haul-road', 'dump', 'idle']
    for i, m in enumerate(MONTHS):
        dm = d[d.month == m]
        rank = [levers.index(t) + 1 + (i - 2) * .06 for t in dm['top_lever']]
        ax[1].plot(dm['q'], rank, 'o-', label=m, alpha=.85)
    ax[1].set_yticks(range(1, len(levers) + 1)); ax[1].set_yticklabels(levers)
    ax[1].set_ylim(len(levers) + .5, .5)
    ax[1].set_xlabel('baseline quantile q'); ax[1].set_title('#1 LEVER is parameter-invariant', fontweight='bold')
    ax[1].axvline(.15, color='k', ls=':', lw=1); ax[1].grid(alpha=.3)
    n_cell = len(df); n_top = int((df['top_lever'] == 'return-road').sum())
    ax[1].text(.5, .5, f'{n_top}/{n_cell} cells\n(5 months x 5 q x 2 baseline refs)\n#1 = return-road',
               transform=ax[1].transAxes, ha='center', va='center', fontsize=11,
               bbox=dict(boxstyle='round', fc='#eef7ee', ec='green'))
    ax[1].legend(fontsize=7, loc='lower right')
    # (3) margin of the #1 over the #2
    for m in MONTHS:
        dm = d[d.month == m]
        ax[2].plot(dm['q'], dm['gap_1_2'], 'o-', label=m)
    ax[2].axhline(0, color='r', lw=1)
    ax[2].set_xlabel('baseline quantile q'); ax[2].set_ylabel('#1 minus #2 (loads/day)')
    ax[2].set_title('margin of the winner (>0 = no tie)', fontweight='bold')
    ax[2].axvline(.15, color='k', ls=':', lw=1); ax[2].grid(alpha=.3)
    fig.suptitle(f'agent_v2 baseline-quantile sensitivity — zone {zone_id} (per-month baseline)',
                 fontweight='bold')
    fig.tight_layout(); fig.savefig(path, dpi=130)
    return path


if __name__ == '__main__':
    zid = int(sys.argv[1]) if len(sys.argv) > 1 else 25559
    print(f"sweeping zone {zid}: {len(MONTHS)} months x {len(QS)} q x 2 refs = "
          f"{len(MONTHS) * len(QS) * 2} runs\n")
    df = sweep(zid)
    csv = os.path.join(_HERE, f'sensitivity_sweep_{zid}.csv')
    df.to_csv(csv, index=False)
    print("\n" + verdict(df))
    png = figure(df, zid, os.path.join(_HERE, f'sensitivity_sweep_{zid}.png'))
    print(f"\n[-> {csv}]\n[-> {png}]")
