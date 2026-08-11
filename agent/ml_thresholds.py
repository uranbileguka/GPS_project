#!/usr/bin/env python3
"""
ml_thresholds.py  —  DATA-DRIVEN replacement for the hand-set L1/L2 dwell cut lines.

STANDALONE & ADDITIVE: this module does NOT import or modify agent_diagnose.py.
It reads the same cache (data/cycles_all_months.csv) and produces the two dwell
cut lines the agent currently hard-codes, but learns them from the data instead:

    agent_diagnose.py (current)          ml_thresholds.py (this file)
    ------------------------------       -----------------------------------------
    QUEUE_CAP = 120 min  (hand-set)  ->  learned per zone from the dwell distribution
                                         via a Gaussian Mixture Model  (queue/work vs long-stop)
    PARK_CAP  = 360 min  (hand-set)  ->  NOT a dwell mode (BIC finds only 2 humps);
                                         the on-shift/off-shift split is decided by a
                                         TIME-OF-DAY signal (does the stop span overnight),
                                         which is month-invariant by construction.

WHY GMM for the first cut:
  A truck's loading-dwell distribution is a mixture of a "working" mode (load + short
  queue, ~15-25 min) and a "parked" mode (overnight, ~14 h). We model log(dwell) as a
  Gaussian mixture, fit by EM (maximum likelihood), and take the cut = the density valley
  (antimode) between the two dominant modes. This is UNSUPERVISED (no cause labels), so it
  keeps the "no ground-truth / interpretable" frame; the cut is derived, reproducible, and
  per-zone/cycle-relative instead of a global constant.

WHY NOT GMM for the second cut:
  Empirically (BN, all months) BIC selects K=2 — the raw dwell density shows only
  work vs long-stop, NO separate "on-shift idle" hump. So 6h is a policy line, not a
  density valley. The right signal for on-shift idle vs off-shift downtime is whether the
  stop overlaps night hours, not how long it is. `classify_stops` uses that instead.

Honesty frame (unchanged): DIAGNOSTIC, not proof. Learned cuts are still an upper-bound
device; no payload; a real gain needs a before/after pilot.
"""
import os
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.mixture import GaussianMixture

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
CYCLES_CSV = os.path.join(_ROOT, 'data', 'cycles_all_months.csv')

STEADY_MONTHS = ['2025-08', '2025-09', '2025-10', '2025-11']   # exclude Jul ramp-up
NIGHT_HOUR = 3          # a stop "spans overnight" if it is still ongoing at 03:00 local
RANDOM_STATE = 0


# ------------------------------------------------------------------ dwell extraction
def load_dwell(zone_id, month=None):
    """Loading dwells for a load zone, mirroring agent_diagnose.perception().

    dwell = next depart_load - this arrive_load  (same truck, consecutive cycles).
    Returns a DataFrame [tracker_id, arrive_load, depart_next, dwell_min]; one row per
    completed loading stop. `month` may be a str '2025-11', a list of str, or None (all).
    """
    C = pd.read_csv(CYCLES_CSV, parse_dates=['depart_load', 'arrive_load'])
    cyc = C[C['load_zone'] == zone_id].copy()
    if month is not None:
        months = [month] if isinstance(month, str) else list(month)
        cyc = cyc[cyc['month'].isin(months)]
    cyc = cyc.sort_values(['tracker_id', 'depart_load'])
    cyc['depart_next'] = cyc.groupby('tracker_id')['depart_load'].shift(-1)
    same = cyc['tracker_id'].eq(cyc['tracker_id'].shift(-1))
    dwell_s = np.where(same, (cyc['depart_next'] - cyc['arrive_load']).dt.total_seconds(), np.nan)
    out = cyc[['tracker_id', 'arrive_load', 'depart_next']].copy()
    out['dwell_min'] = dwell_s / 60.0
    out = out[(out['dwell_min'] > 0)].dropna(subset=['dwell_min']).reset_index(drop=True)
    return out


# ------------------------------------------------------------------ the ML core: GMM
def fit_dwell_gmm(dwell_min, k_range=range(1, 6)):
    """Fit a Gaussian Mixture on log(dwell) and report the model + BIC sweep.

    Returns a dict:
      best_k       : K minimising BIC
      bic_by_k     : {K: BIC}
      components   : list (sorted by mean) of {weight, mean_min, sigma_log}
      cut_points   : all density antimodes of the BIC-best model, in minutes
    """
    x = np.log(np.asarray(dwell_min, float)).reshape(-1, 1)
    bic_by_k, models = {}, {}
    for k in k_range:
        g = GaussianMixture(k, n_init=8, random_state=RANDOM_STATE).fit(x)
        bic_by_k[k] = float(g.bic(x))
        models[k] = g
    best_k = min(bic_by_k, key=bic_by_k.get)
    g = models[best_k]

    order = np.argsort(g.means_.ravel())
    comps = [dict(weight=float(g.weights_[i]),
                  mean_min=float(np.exp(g.means_.ravel()[i])),
                  sigma_log=float(np.sqrt(g.covariances_.ravel()[i])))
             for i in order]
    cut_points = _antimodes(g, x) if best_k > 1 else []
    return dict(best_k=best_k, bic_by_k=bic_by_k, components=comps,
                cut_points=cut_points, _gmm=g)


def _mixture_density(g, xs):
    """Total mixture density at log-points xs (1-D)."""
    w = g.weights_; mu = g.means_.ravel(); sd = np.sqrt(g.covariances_.ravel())
    return sum(w[k] * norm.pdf(xs, mu[k], sd[k]) for k in range(len(w)))


def _antimodes(g, x):
    """Density valleys (local minima) of the mixture, between the extreme means, in minutes."""
    mu = np.sort(g.means_.ravel())
    xs = np.linspace(mu[0], mu[-1], 4000)
    d = _mixture_density(g, xs)
    mins = [i for i in range(1, len(xs) - 1) if d[i] < d[i - 1] and d[i] < d[i + 1]]
    return [float(np.exp(xs[i])) for i in mins]


def fit_two_modes(dwell_min):
    """The recommended, interpretable split: force K=2 (work/queue vs long-stop).

    BIC's extra modes on this data are tiny sub-minute re-departures, not the question we
    care about, so we fix K=2. Returns (work_min, park_min, w_work, cut_min) — the two
    mode centres, the working-mode weight, and the density antimode strictly between them.
    """
    x = np.log(np.asarray(dwell_min, float)).reshape(-1, 1)
    g = GaussianMixture(2, n_init=10, random_state=RANDOM_STATE).fit(x)
    o = np.argsort(g.means_.ravel())
    mu = g.means_.ravel()[o]; w = g.weights_[o]
    xs = np.linspace(mu[0], mu[1], 4000)
    cut = float(np.exp(xs[int(np.argmin(_mixture_density(g, xs)))]))
    return float(np.exp(mu[0])), float(np.exp(mu[1])), float(w[0]), cut


def robust_queue_cut(dwell_min):
    """Just the recommended single cut (work/queue <-> long-stop), in minutes."""
    return fit_two_modes(dwell_min)[3]


# ------------------------------------------------------------------ 2nd cut: overnight
def _spans_overnight(t0, t1, hour=NIGHT_HOUR):
    """True if the stop interval [t0, t1] is still ongoing at `hour`:00 on some day."""
    if pd.isna(t0) or pd.isna(t1):
        return False
    mark = t0.normalize() + pd.Timedelta(hours=hour)
    if mark < t0:
        mark += pd.Timedelta(days=1)
    return mark <= t1


def classify_stops(dwell_df, queue_cut_min):
    """Split every loading stop into working / on-shift idle / off-shift downtime.

    working        : dwell <= queue_cut_min          (load + short queue)
    on_shift_idle  : dwell  > queue_cut_min, NOT overnight   (recoverable-ish)
    downtime       : dwell  > queue_cut_min, overnight       (staffing, not dispatch)
    Returns the df with a 'state' column plus a small summary (count & truck-hours each).
    """
    df = dwell_df.copy()
    overnight = df.apply(lambda r: _spans_overnight(r['arrive_load'], r['depart_next']), axis=1)
    long = df['dwell_min'] > queue_cut_min
    df['state'] = np.where(~long, 'working',
                    np.where(overnight, 'downtime', 'on_shift_idle'))
    summ = (df.groupby('state')['dwell_min']
              .agg(n='size', truck_h=lambda s: s.sum() / 60.0)
              .round(1))
    return df, summ


# ------------------------------------------------------------------ per-zone learning
def per_month_table(zone_id, months=STEADY_MONTHS + ['2025-07']):
    """Stability diagnostic: fit the robust K=2 cut per month; show the drift."""
    rows = []
    for m in sorted(months):
        d = load_dwell(zone_id, m)['dwell_min']
        if len(d) < 50:
            continue
        work, park, w_work, cut = fit_two_modes(d)      # all from the same K=2 model
        rows.append(dict(month=m, n=len(d),
                         work_min=round(work, 1),
                         park_min=round(park, 1),
                         w_work=round(w_work, 2),
                         bic_k=fit_dwell_gmm(d)['best_k'],   # informational only
                         cut_min=round(cut, 1)))
    return pd.DataFrame(rows)


def learn_thresholds(zone_id, freeze_on=STEADY_MONTHS):
    """Learn the two thresholds the agent needs, each by the RIGHT method.

    Returns a dict ready to be *passed into* a diagnosis run (the agent is NOT modified):
      queue_cut_min : frozen work<->long-stop cut, pooled over the steady-state months
      overnight_hour: the time-of-day marker used for the on-shift/off-shift split
      method / per_month / notes : provenance for the paper
    """
    pooled = load_dwell(zone_id, freeze_on)['dwell_min']
    cut = round(robust_queue_cut(pooled), 1)
    tbl = per_month_table(zone_id)
    return dict(
        zone_id=zone_id,
        queue_cut_min=cut,
        overnight_hour=NIGHT_HOUR,
        freeze_on=list(freeze_on),
        method='GMM(K=2) antimode on log(dwell); frozen on steady-state months',
        second_cut_method='time-of-day: stop spans overnight (not a dwell mode)',
        per_month=tbl.to_dict('records'),
        notes=['UNSUPERVISED (no cause labels) -> keeps interpretable frame',
               'freeze one cut for cross-month comparability; per_month is a stability check',
               'Jul is ramp-up (separate regime) -> excluded from the frozen cut',
               'upper-bound device; no payload; needs before/after pilot'])


# ------------------------------------------------------------------ plotting helper
def plot_dwell_gmm(dwell_min, result=None, handset=(120, 360), ax=None, title=None):
    """Histogram of log-dwell + fitted component curves + learned vs hand-set cuts."""
    import matplotlib.pyplot as plt
    if result is None:
        result = fit_dwell_gmm(dwell_min)
    g = result['_gmm']
    x = np.log(np.asarray(dwell_min, float))
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(x, bins=60, density=True, color='0.85', edgecolor='white', label='log-dwell (data)')
    xs = np.linspace(x.min(), x.max(), 800)
    w, mu, sd = g.weights_, g.means_.ravel(), np.sqrt(g.covariances_.ravel())
    for k in np.argsort(mu):
        ax.plot(xs, w[k] * norm.pdf(xs, mu[k], sd[k]),
                label=f'mode ~{np.exp(mu[k]):.0f} min (w={w[k]:.2f})')
    ax.plot(xs, _mixture_density(g, xs), 'k--', lw=1, alpha=.7, label='mixture')
    for c in result['cut_points']:
        ax.axvline(np.log(c), color='C3', lw=2, label=f'learned cut {c:.0f} min')
    for h in handset:
        ax.axvline(np.log(h), color='C0', ls=':', lw=1.5, label=f'hand-set {h} min')
    # readable x ticks in minutes
    ticks = [5, 15, 30, 60, 120, 360, 1440, 4320]
    ax.set_xticks([np.log(t) for t in ticks]); ax.set_xticklabels([str(t) for t in ticks])
    ax.set_xlabel('dwell (minutes, log scale)'); ax.set_ylabel('density')
    ax.set_title(title or 'Loading dwell — learned modes & cut vs hand-set lines')
    ax.legend(fontsize=8, loc='upper right')
    return ax


# ------------------------------------------------------------------ CLI
if __name__ == '__main__':
    import sys
    zid = int(sys.argv[1]) if len(sys.argv) > 1 else 25559
    d_nov = load_dwell(zid, '2025-11')['dwell_min']
    res = fit_dwell_gmm(d_nov)
    print(f"=== zone {zid}, 2025-11 ({len(d_nov)} dwells) ===")
    print("BIC by K:", {k: round(v, 1) for k, v in res['bic_by_k'].items()}, "-> best K =", res['best_k'])
    for i, c in enumerate(res['components'], 1):
        print(f"  mode {i}: ~{c['mean_min']:.1f} min   weight {c['weight']:.2f}")
    print("learned cut(s) (BIC model):", [round(c, 1) for c in res['cut_points']])
    print("robust K=2 queue cut       :", round(robust_queue_cut(d_nov), 1), "min",
          "  (hand-set was 120)")
    print("\n--- per-month stability ---")
    print(per_month_table(zid).to_string(index=False))
    lt = learn_thresholds(zid)
    print(f"\nFROZEN queue_cut = {lt['queue_cut_min']} min   (steady-state {lt['freeze_on']})")
    _, summ = classify_stops(load_dwell(zid, '2025-11'), lt['queue_cut_min'])
    print("\n--- Nov stops split with the frozen cut + overnight rule ---")
    print(summ.to_string())
