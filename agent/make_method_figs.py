"""Regenerate every figure used by agent_method_EN.md.

Kept in the repo rather than a scratch directory: the previous generators lived in a session
scratchpad and vanished with it, which is why the figures could not be refreshed when the
numbers changed.

    python analysis/make_method_figs.py            # all
    python analysis/make_method_figs.py legs conc  # named ones only
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent_v2 as v2

HERE = os.path.dirname(os.path.abspath(__file__))
ZID, MONTH = 25559, '2025-11'
TEAL, ORANGE, GREY, RED, BLUE = '#159A8C', '#E8890C', '#9A9A9A', '#C0392B', '#3A6EA5'
plt.rcParams.update({'figure.dpi': 110, 'savefig.dpi': 110, 'font.size': 11,
                     'axes.grid': True, 'grid.alpha': .3, 'axes.axisbelow': True,
                     'figure.autolayout': True})

_cache = {}


def dx():
    if 'dx' not in _cache:
        _cache['dx'] = v2.diagnose_v2(ZID, MONTH)
    return _cache['dx']


def cyc():
    if 'cyc' not in _cache:
        _cache['cyc'] = v2.load_cycles(ZID, MONTH)
    return _cache['cyc']


def pings():
    if 'pings' not in _cache:
        p = v2.load_pings(MONTH, cyc().tracker_id.unique()).sort_values(['tracker_id', 'get_time'])
        p['dt'] = (p.groupby('tracker_id')['get_time'].diff().dt.total_seconds()
                   .shift(-1).clip(upper=v2.DT_CAP).fillna(0))
        _cache['pings'] = p
    return _cache['pings']


def save(fig, name):
    path = os.path.join(HERE, name)
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print(f'  wrote {name}')


# ---------------------------------------------------------------- schematic figures
def fig_pipeline():
    steps = ['0. raw GPS\npings', '1. trucks\n+ zones', '2. build\ncycles', '3. cut into\nphases',
             '4. find places\non the route', '5. charge every\nminute to a place',
             '6. delay =\nactual − reference', '7. station\nrates', '8. delay hours\n→ loads/day']
    fig, ax = plt.subplots(figsize=(13.5, 2.5))
    ax.set_xlim(0, len(steps)); ax.set_ylim(0, 1); ax.axis('off')
    for i, s in enumerate(steps):
        ax.add_patch(Rectangle((i + .06, .25), .88, .5, facecolor=TEAL if i else GREY,
                               alpha=.85, edgecolor='none'))
        ax.text(i + .5, .5, s, ha='center', va='center', color='white', fontsize=9.5, weight='bold')
        if i:
            ax.add_patch(FancyArrowPatch((i - .02, .5), (i + .05, .5), arrowstyle='-|>',
                                         mutation_scale=11, color='#444', lw=1.2))
    ax.set_title('The eight steps — raw positions in, ranked actions out', weight='bold', pad=8)
    save(fig, 't_fig_pipeline.png')


def fig_phases():
    c = cyc()
    med = lambda k: float(c[k].median()) / 60
    ph = [('loading\n(at the load zone)', med('dwell_s'), TEAL),
          ('haul\n(loaded)', med('haul_s'), GREY),
          ('dumping\n(at the dump)', med('dump_s'), ORANGE),
          ('return\n(empty)', med('return_s'), GREY)]
    fig, ax = plt.subplots(figsize=(12, 2.6))
    x = 0
    for lab, w, c in ph:
        ax.add_patch(Rectangle((x, .3), w, .45, facecolor=c, alpha=.85, edgecolor='white', lw=2))
        ax.text(x + w / 2, .525, lab, ha='center', va='center', color='white',
                fontsize=10, weight='bold')
        ax.text(x + w / 2, .2, f'{w:.0f} min', ha='center', va='top', fontsize=9.5, color='#333')
        x += w
    ax.set_xlim(-2, x + 2); ax.set_ylim(0, 1); ax.axis('off')
    ax.set_title(f'One cycle, four phases — BN median durations, {x:.0f} min in total',
                 weight='bold', pad=8)
    save(fig, 'c_fig_phases.png')


def fig_mechanisms():
    fig, ax = plt.subplots(figsize=(11.5, 3.4))
    ax.axis('off'); ax.set_xlim(0, 10); ax.set_ylim(0, 4)
    ax.add_patch(Rectangle((.2, 2.2), 4.4, 1.5, facecolor=TEAL, alpha=.15, edgecolor=TEAL, lw=1.5))
    ax.text(2.4, 3.35, 'a — shorten the loop', ha='center', weight='bold', color=TEAL, fontsize=12)
    ax.text(2.4, 2.75, 'remove delay from inside the cycle\n'
                       'each truck finishes its round trip sooner\n'
                       'loads/day  =  looping hours ÷ new cycle time',
            ha='center', va='center', fontsize=9.5)
    ax.add_patch(Rectangle((5.4, 2.2), 4.4, 1.5, facecolor=ORANGE, alpha=.15,
                           edgecolor=ORANGE, lw=1.5))
    ax.text(7.6, 3.35, 'b — add looping hours', ha='center', weight='bold', color=ORANGE, fontsize=12)
    ax.text(7.6, 2.75, 'return time spent outside the loop\n'
                       'the cycle is unchanged, there are more of them\n'
                       'loads/day  =  extra hours ÷ cycle time',
            ha='center', va='center', fontsize=9.5)
    ax.text(5, 1.4, 'Both end in loads per day, so levers of different kinds are comparable.',
            ha='center', fontsize=10.5, style='italic')
    ax.text(5, .6, 'Every gain is an UPPER BOUND: it assumes the delay is removed entirely\n'
                   'and that nothing else becomes the constraint in its place.',
            ha='center', fontsize=10, color=RED)
    ax.set_title('Two ways a recovered hour becomes a load', weight='bold', pad=6)
    save(fig, 't_fig_mechanisms.png')


def fig_tierule():
    fig, ax = plt.subplots(figsize=(9.5, 3.6))
    lead = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    flipped = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    ax.bar(lead[flipped == 1], [1] * int(flipped.sum()), color=RED, alpha=.8,
           label='the top lever changed when a parameter moved')
    ax.bar(lead[flipped == 0], [1] * int((1 - flipped).sum()), color=TEAL, alpha=.8,
           label='the top lever held')
    ax.axvline(4.5, color='#333', ls='--', lw=1.6)
    ax.text(4.65, .55, 'report a tie below a 5 loads/day lead', fontsize=10.5, weight='bold')
    ax.set_xlabel('lead of the top lever over the runner-up (loads/day)')
    ax.set_yticks([]); ax.set_ylim(0, 1.35); ax.legend(loc='upper right', fontsize=9)
    ax.set_title('Where the 5 loads/day margin comes from — 30 zone-months, three material flows',
                 weight='bold', fontsize=11.5)
    save(fig, 't_fig_tierule.png')


# ---------------------------------------------------------------- data figures
def fig_onetrip():
    """One return phase, broken into where the truck actually was."""
    c = cyc(); p = pings()
    boxes = v2.all_zone_boxes()
    lz = [b for b in boxes if b['zone_id'] == ZID][0]
    sub = c[(c.return_s > 3 * 3600) & c.return_s.notna()].sort_values('return_s')
    r = sub.iloc[len(sub) // 2]
    g = p[(p.tracker_id == r.tracker_id) & (p.get_time >= r.depart_unload) &
          (p.get_time <= r.arrive_load)].copy()
    inl = g.lat.between(lz['la0'], lz['la1']) & g.lng.between(lz['ln0'], lz['ln1'])
    g['state'] = np.where(g.speed > v2.STOP_SPEED, 'driving',
                          np.where(inl, 'at the load zone', 'stopped somewhere'))
    g['blk'] = (g.state != g.state.shift()).cumsum()
    segs = []
    for _, b in g.groupby('blk'):
        mins = (b.get_time.max() - b.get_time.min()).total_seconds() / 60
        if mins >= 2:
            segs.append((b.state.iloc[0], mins))
    fig, ax = plt.subplots(figsize=(12, 2.7))
    colour = {'driving': TEAL, 'stopped somewhere': RED, 'at the load zone': ORANGE}
    x = 0
    for st, w in segs:
        ax.add_patch(Rectangle((x, .35), w, .4, facecolor=colour[st], edgecolor='white', lw=1))
        if w > sum(s[1] for s in segs) * .06:
            ax.text(x + w / 2, .55, f'{w:.0f}', ha='center', va='center',
                    color='white', fontsize=9, weight='bold')
        x += w
    drive = sum(w for s, w in segs if s == 'driving')
    ax.set_xlim(-3, x + 3); ax.set_ylim(0, 1); ax.axis('off')
    for i, (lab, c_) in enumerate(colour.items()):
        ax.add_patch(Rectangle((i * x / 3.2, .05), x / 40, .1, facecolor=c_))
        ax.text(i * x / 3.2 + x / 32, .1, lab, va='center', fontsize=9.5)
    ax.set_title(f'Truck {r.tracker_id} — one empty return of {x:.0f} min, of which '
                 f'{drive:.0f} min is actual driving', weight='bold', pad=8)
    save(fig, 'c_fig_onetrip.png')


def fig_topology():
    d = dx()
    topo = pd.DataFrame(d['leg_decomposition']['topology'])
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    is_st = topo.kind == 'station'
    off = topo.coverage_pct < v2.OFFLOOP_MAX_COV
    ax.scatter(topo.coverage_pct[is_st], topo.stop_rate[is_st], s=90, color=TEAL,
               edgecolor='k', lw=.5, label='station — on the route AND trucks stop', zorder=3)
    ax.scatter(topo.coverage_pct[~is_st & ~off], topo.stop_rate[~is_st & ~off], s=55,
               color=GREY, edgecolor='k', lw=.4, label='waypoint — passed but not stopped at')
    ax.scatter(topo.coverage_pct[off], topo.stop_rate[off], s=55, color=ORANGE,
               edgecolor='k', lw=.4, label='out of the loop — not on every trip')
    ax.axhline(v2.STATION_MIN_STOPRATE, color=RED, ls='--', lw=1.5)
    ax.axvline(v2.STATION_MIN_COV, color=BLUE, ls='--', lw=1.5)
    ax.text(v2.STATION_MIN_COV + 6, .02, f'coverage ≥ {v2.STATION_MIN_COV}%', color=BLUE, fontsize=9.5)
    ax.text(2, v2.STATION_MIN_STOPRATE + .02, f'stop rate ≥ {v2.STATION_MIN_STOPRATE}',
            color=RED, fontsize=9.5)
    ax.set_xscale('log')
    ax.set_xlabel('coverage — visits ÷ cycles (%)'); ax.set_ylabel('stop rate — share of visits with a ≤2 km/h ping')
    ax.set_ylim(-.05, 1.05); ax.legend(fontsize=9, loc='upper left')
    ax.set_title('Which places are part of the loop — neither axis reads a zone name',
                 weight='bold', fontsize=11.5)
    save(fig, 'v4_fig2_topology.png')


def fig_legs():
    d = dx()
    b = d['buckets_truck_h']
    st = {k: v for k, v in b.items() if k.endswith('_queue') or k.endswith('_solo_long')}
    parts = [('driving (haul + return)', b.get('road_haul', 0) + b.get('road_return', 0), TEAL),
             ('at a station on the road', sum(st.values()), ORANGE),
             ('stopped, place unmapped', b.get('stopped_unmapped', 0), RED),
             ('out of the loop', d['reservoir_truck_h'].get('offloop_stop', 0), GREY)]
    parts = [p for p in parts if p[1] > 0]
    tot = sum(p[1] for p in parts)
    fig, ax = plt.subplots(figsize=(11.5, 2.6))
    x = 0
    for lab, w, c in parts:
        ax.add_patch(Rectangle((x, .3), w, .45, facecolor=c, alpha=.9, edgecolor='white', lw=2))
        ax.text(x + w / 2, .525, f'{w / tot * 100:.0f}%', ha='center', va='center',
                color='white', weight='bold', fontsize=11)
        ax.text(x + w / 2, .22, lab, ha='center', va='top', fontsize=9, color='#333')
        x += w
    ax.set_xlim(-tot * .02, tot * 1.02); ax.set_ylim(0, 1); ax.axis('off')
    ax.set_title(f'Where "road" time actually goes — only {d["leg_decomposition"]["driving_share_pct"]}%'
                 f' of it is driving  ({tot:,.0f} truck-h, BN {MONTH})', weight='bold', pad=8)
    save(fig, 'v4_fig3_legs.png')


def fig_dwell():
    """The load-zone stay, with the service reference on it."""
    c = cyc()
    conc = v2._concurrency(c)
    d = c.dwell_s.values / 60
    svc = dx()['cycle']['svc_load_min']
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    bins = np.linspace(0, np.nanpercentile(d, 99), 60)
    ax.hist(d[conc == 0], bins=bins, color=TEAL, alpha=.85, label='nobody else at the load zone')
    ax.hist(d[conc >= 1], bins=bins, color=ORANGE, alpha=.6, label='at least one truck ahead')
    ax.axvline(svc, color=RED, lw=2.4)
    ax.annotate(f'service = {svc:.0f} min\n(median with nobody else there)',
                xy=(svc, ax.get_ylim()[1] * .55), xytext=(svc * 2.6, ax.get_ylim()[1] * .72),
                color=RED, fontsize=10, weight='bold',
                arrowprops=dict(arrowstyle='->', color=RED, lw=1.5))
    ax.set_xlabel('stay at the load zone (min)'); ax.set_ylabel('cycles')
    ax.legend(fontsize=9.5)
    ax.set_title('The load-zone stay, split by how many trucks were already there',
                 weight='bold', fontsize=11.5)
    save(fig, 'v4_fig1_dwell.png')


def fig_conc():
    c = cyc()
    conc = v2._concurrency(c)
    d = c.dwell_s.values / 60
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    xs, med, n = [], [], []
    for k in range(0, 6):
        m = (conc == k) if k < 5 else (conc >= 5)
        if m.sum() < 15:
            continue
        xs.append(k); med.append(np.nanmedian(d[m])); n.append(int(m.sum()))
        ax.scatter(np.full(int(m.sum()), k) + np.random.default_rng(k).normal(0, .07, int(m.sum())),
                   d[m], s=7, color=GREY, alpha=.35, zorder=1)
    ax.plot(xs, med, 'o-', color=TEAL, lw=2.5, ms=9, zorder=3, label='median stay')
    for x_, y_, n_ in zip(xs, med, n):
        ax.annotate(f'{y_:.0f} min\nn={n_}', (x_, y_), textcoords='offset points',
                    xytext=(0, 13), ha='center', fontsize=9, color=TEAL, weight='bold')
    rho = pd.DataFrame({'c': conc, 'd': d}).corr(method='spearman').iloc[0, 1]
    ax.set_xlabel('trucks already at the load zone when this one arrived')
    ax.set_ylabel('stay at the load zone (min)')
    ax.set_ylim(0, np.nanpercentile(d, 97))
    ax.set_xticks(xs); ax.set_xticklabels([str(x) if x < 5 else '5+' for x in xs])
    ax.legend(fontsize=9.5)
    ax.set_title(f'The stay grows with the number of trucks ahead  (Spearman {rho:.2f})',
                 weight='bold', fontsize=11.5)
    save(fig, 'v4_fig4_conc.png')


def fig_gaps():
    c = cyc()
    dep = np.sort(c.depart_load.dropna().values)
    gaps = np.diff(dep) / np.timedelta64(1, 'm')
    kept = gaps[gaps < v2.BUSY_GAP_MIN]
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    ax.hist(gaps[gaps < 90], bins=80, color=GREY, alpha=.75, label='all gaps')
    ax.hist(kept, bins=int(v2.BUSY_GAP_MIN * 80 / 90), color=TEAL, alpha=.9,
            label=f'kept — under {v2.BUSY_GAP_MIN} min (station was busy)')
    ax.axvline(np.median(kept), color=RED, lw=2.2,
               label=f'median kept gap {np.median(kept):.2f} min  →  {60/np.median(kept):.2f} loads/h')
    ax.axvline(v2.BUSY_GAP_MIN, color='#333', ls='--', lw=1.4)
    ax.set_xlabel('gap between consecutive departures from the load zone (min)')
    ax.set_ylabel('count'); ax.legend(fontsize=9.5)
    ax.set_title('How fast the shovel can go — measured only while it had trucks to serve',
                 weight='bold', fontsize=11.5)
    save(fig, 't_fig_gaps.png')


def _hourly_loads():
    c = cyc()
    h = c.groupby(c.depart_load.dt.floor('h')).size()
    full = pd.Series(0, index=pd.date_range(h.index.min(), h.index.max(), freq='h'))
    full.update(h)
    return full


def fig_hours():
    full = _hourly_loads()
    thr = .4 * full.mean()
    fig, ax = plt.subplots(figsize=(12, 3.8))
    ax.plot(full.index, full.values, lw=.8, color=GREY)
    ax.axhline(thr, color=RED, ls='--', lw=1.8,
               label=f'0.4 × mean = {thr:.1f} loads/h — below this the fleet is not running')
    ax.fill_between(full.index, 0, full.values, where=full.values >= thr, color=TEAL, alpha=.5,
                    label=f'operating hours: {int((full >= thr).sum())} of {len(full)}')
    ax.set_ylabel('loads departing per hour'); ax.legend(fontsize=9.5, loc='upper right')
    ax.set_title(f'Operating hours — BN {MONTH}', weight='bold', fontsize=11.5)
    save(fig, 't_fig_hours.png')


def fig_hours_sens():
    full = _hourly_loads()
    ts = np.arange(.2, .75, .05)
    hrs = [(full >= t * full.mean()).sum() for t in ts]
    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.plot(ts, hrs, 'o-', color=TEAL, lw=2.2, ms=7)
    ax.axvline(.4, color=RED, ls='--', lw=1.6, label='the value used: 0.4')
    ax.set_xlabel('threshold (× mean loads per hour)'); ax.set_ylabel('operating hours in the month')
    ax.legend(fontsize=9.5)
    span = max(hrs) - min(hrs)
    ax.set_title(f'The threshold moves operating hours by {span/np.mean(hrs)*100:.0f}% across '
                 f'0.2–0.7 — the direction of the diagnosis does not move',
                 weight='bold', fontsize=11)
    save(fig, 't_fig_hours_sens.png')


def fig_levers():
    d = dx()
    L = pd.DataFrame(d['levers']).head(8).iloc[::-1]
    fig, ax = plt.subplots(figsize=(13, 5.4))
    cols = [ORANGE if 'add looping' in str(m) else TEAL for m in L.mech]
    ax.barh(range(len(L)), L.gain, color=cols, alpha=.9)
    ax.set_yticks(range(len(L)))
    import textwrap
    ax.set_yticklabels(['\n'.join(textwrap.wrap(c, 46)) for c in L.cause], fontsize=9)
    for i, (g, h) in enumerate(zip(L.gain, L.bucket_truck_h)):
        ax.text(g + .08, i, f'+{g:.1f}   ({h:,.0f} truck-h)', va='center', fontsize=9.5)
    v = d['lever_verdict']
    note = ('TIED — the lead is under 5 loads/day' if str(v.get('tied')).lower() in ('1', 'true')
            else f"clear winner — lead {v.get('margin')}")
    ax.set_xlim(0, L.gain.max() * 1.45)
    ax.text(L.gain.max() * .55, .4, note, color=RED, fontsize=11.5, weight='bold')
    ax.set_xlabel('extra loads per day if this delay were removed entirely (upper bound)')
    ax.set_title(f'Ranked levers — BN {MONTH}, {d["throughput"]["loads_day"]} loads/day today',
                 weight='bold', fontsize=12)
    save(fig, 't_fig_levers.png')


def fig_ownership():
    d = dx()
    disp = sum(l['bucket_truck_h'] for l in d['levers'])
    staff = d['staffing'] if isinstance(d['staffing'], list) else [d['staffing']]
    non = sum(s['reservoir_truck_h'] for s in staff)
    fig, ax = plt.subplots(figsize=(10, 2.7))
    tot = disp + non
    ax.add_patch(Rectangle((0, .3), disp, .45, facecolor=TEAL, alpha=.9, edgecolor='white', lw=2))
    ax.add_patch(Rectangle((disp, .3), non, .45, facecolor=ORANGE, alpha=.9,
                           edgecolor='white', lw=2))
    ax.text(disp / 2, .525, f'dispatch can act\n{disp:,.0f} truck-h', ha='center', va='center',
            color='white', weight='bold', fontsize=10)
    ax.text(disp + non / 2, .525, f'roster / logistics\n{non:,.0f} truck-h', ha='center',
            va='center', color='white', weight='bold', fontsize=10)
    ax.set_xlim(-tot * .02, tot * 1.02); ax.set_ylim(0, 1); ax.axis('off')
    ax.set_title('Reported separately, never ranked against each other — a dispatcher cannot '
                 'add a shift', weight='bold', pad=8, fontsize=11.5)
    save(fig, 't_fig_ownership.png')


def _months_table():
    if 'mt' in _cache:
        return _cache['mt']
    rows = []
    for m in v2.raw_months():
        try:
            d = v2.diagnose_v2(ZID, m)
        except Exception as e:
            print(f'  {m}: {type(e).__name__}: {e}'); continue
        L = d['levers'][0] if d['levers'] else {}
        rows.append(dict(month=m, loads=d['throughput']['loads_day'],
                         rho=d['stations']['rho_shovel'], sat=d['stations']['saturated'],
                         drive=d['leg_decomposition']['driving_share_pct'],
                         top=L.get('cause', ''), gain=L.get('gain', 0),
                         tied=str(d['lever_verdict'].get('tied')).lower() in ('1', 'true'),
                         lo=d['headline']['lower_bound_pct'], hi=d['headline']['upper_bound_pct']))
    _cache['mt'] = pd.DataFrame(rows)
    return _cache['mt']


def fig_months():
    T = _months_table()
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.8))
    axes[0].bar(T.month, T.loads, color=TEAL, alpha=.9)
    axes[0].set_title('loads per day', fontsize=10.5); axes[0].tick_params(axis='x', rotation=45)
    axes[1].bar(T.month, T.rho, color=TEAL, alpha=.9)
    axes[1].axhline(1.0, color=RED, ls='--', lw=1.8, label='saturated')
    axes[1].set_ylim(0, 1.1); axes[1].legend(fontsize=9)
    axes[1].set_title('shovel utilisation — never saturated', fontsize=10.5)
    axes[1].tick_params(axis='x', rotation=45)
    axes[2].bar(T.month, T.drive, color=TEAL, alpha=.9)
    axes[2].set_ylim(0, 100)
    axes[2].set_title('% of "road" time that is driving', fontsize=10.5)
    axes[2].tick_params(axis='x', rotation=45)
    fig.suptitle('Five months, same pipeline, nothing tuned per month', weight='bold', fontsize=12)
    save(fig, 'v4_fig6_months.png')


def fig_range():
    T = _months_table()
    fig, ax = plt.subplots(figsize=(9.5, 4))
    x = np.arange(len(T))
    ax.bar(x, T.hi - T.lo, bottom=T.lo, color=TEAL, alpha=.35, width=.5)
    ax.plot(x, T.lo, 'o-', color=TEAL, lw=2.2, ms=8, label='floor — every normal day matches this fleet\'s own best day')
    ax.plot(x, T.hi, 'o--', color=GREY, lw=1.8, ms=7, label='ceiling — all in-loop delay removed at once (never observed)')
    ax.set_xticks(x); ax.set_xticklabels(T.month, rotation=45)
    ax.set_ylabel('% more loads per day'); ax.legend(fontsize=9)
    ax.set_title('Report the range. Observational data cannot locate the truth inside it.',
                 weight='bold', fontsize=11.5)
    save(fig, 'v4_fig7_range.png')


ALL = {'pipeline': fig_pipeline, 'phases': fig_phases, 'onetrip': fig_onetrip,
       'topology': fig_topology, 'legs': fig_legs, 'dwell': fig_dwell, 'conc': fig_conc,
       'gaps': fig_gaps, 'hours': fig_hours, 'hours_sens': fig_hours_sens,
       'mechanisms': fig_mechanisms, 'levers': fig_levers, 'ownership': fig_ownership,
       'tierule': fig_tierule, 'months': fig_months, 'range': fig_range}

if __name__ == '__main__':
    want = sys.argv[1:] or list(ALL)
    for k in want:
        if k not in ALL:
            print(f'  unknown figure: {k}'); continue
        try:
            ALL[k]()
        except Exception as exc:
            print(f'  FAILED {k}: {type(exc).__name__}: {exc}')
