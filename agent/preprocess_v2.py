"""Offline precompute for the diagnosis specialist in gps_fleet_agent.ipynb.

Same contract as preprocessing.py: do the expensive work once, here, and write a small file
under data/agent_data/ so the notebook's specialist only ever reads JSON. That matters more
for this layer than for the others — diagnose_v2() builds the cycle table from raw GPS and
decomposes every ping onto the discovered station topology, which cannot happen in a chat
turn.

This script does not touch preprocessing.py or anything it writes; it adds files with its
own names to the same folder.

    python agent/preprocess_v2.py                 # every zone, every month with raw GPS
    python agent/preprocess_v2.py 25559 2025-11   # one zone, one month

Writes, under data/agent_data/:
    diagnosis_<zone_id>_<YYYY-MM>.json    full diagnose_v2() output
    diagnosis_index.csv                   one row per (zone, month) that succeeded
"""
import glob
import json
import os
import sys

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import agent_v2 as v2

AGENT_DATA_DIR = os.path.join(v2.DATA_DIR, 'agent_data')


def _norm_month(month: str) -> str:
    """2025-7 -> 2025-07, so these filenames sort alongside preprocessing.py's."""
    year, mon = month.split('-')
    return f"{int(year)}-{int(mon):02d}"


def build_one(zone_id: int, month: str, out_dir: str = None) -> dict:
    out_dir = out_dir or AGENT_DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    month = _norm_month(month)
    dx = v2.diagnose_v2(zone_id, month)
    path = os.path.join(out_dir, f"diagnosis_{zone_id}_{month}.json")
    with open(path, 'w') as fh:
        json.dump(dx, fh, indent=2, ensure_ascii=False, default=str)
    return dx


def _index_row(dx: dict) -> dict:
    """One line per diagnosis — what a question like "which month was worst" filters on."""
    top = dx['levers'][0] if dx.get('levers') else {}
    return {
        'zone_id': dx['zone_id'], 'zone_name': dx['name'], 'region': dx['region'],
        'month': dx['month'],
        'loads_day': dx['throughput']['loads_day'], 'trucks': dx['throughput']['trucks'],
        'top_lever': top.get('cause'), 'top_lever_gain': top.get('gain'),
        'tied': dx['lever_verdict'].get('tied'),
        'binding_station': dx['stations'].get('binding'),
        'saturated': dx['stations'].get('saturated'),
        'driving_share_pct': dx['leg_decomposition'].get('driving_share_pct'),
        # the two headline measurements, each on its own. They replaced a lower/upper pair
        # that was being read as one interval; lower_bound_pct/upper_bound_pct no longer
        # exist, so these two columns had been silently empty.
        'day_spread_pct': dx['headline'].get('day_spread_pct'),
        'explained_pct': dx['headline'].get('explained_pct'),
        'unexplained_pct': dx['headline'].get('unexplained_pct'),
        'dispatch_share_pct': dx['headline'].get('dispatch_share_pct'),
    }


def build_all(zone_ids=None, months=None, out_dir: str = None) -> pd.DataFrame:
    out_dir = out_dir or AGENT_DATA_DIR
    os.makedirs(out_dir, exist_ok=True)
    zone_ids = zone_ids or [25559]          # BN only — see the scope note in agent_method_EN.md
    months = months or v2.raw_months()
    if not months:
        print(f"No gps_data_<year>-<month>.csv found in {v2.DATA_DIR}.")
        return pd.DataFrame()

    rows, failed = [], []
    for zid in zone_ids:
        for month in months:
            label = f"{zid} {month}"
            try:
                dx = build_one(zid, month, out_dir)
                rows.append(_index_row(dx))
                top = dx['levers'][0]['cause'] if dx.get('levers') else '(none)'
                print(f"  ok    {label}  {dx['throughput']['loads_day']} loads/day  #1 {top[:44]}")
            except Exception as exc:
                failed.append((label, f"{type(exc).__name__}: {exc}"))
                print(f"  FAIL  {label}  {type(exc).__name__}: {exc}")

    # The index covers every diagnosis on disk, not just the ones this run rebuilt. Building
    # it from `rows` alone meant `preprocess_v2.py 25559 2025-11` left an index with a single
    # month in it and the other four silently gone.
    idx = pd.DataFrame([_index_row(json.load(open(p)))
                        for p in sorted(glob.glob(os.path.join(out_dir, 'diagnosis_*_*.json')))])
    if not idx.empty:
        idx.sort_values(['zone_id', 'month'], inplace=True)
        idx.to_csv(os.path.join(out_dir, 'diagnosis_index.csv'), index=False)
        print(f"\nWrote {len(rows)} diagnoses; diagnosis_index.csv now lists {len(idx)} "
              f"in {out_dir}")
    for label, msg in failed:
        print(f"  failed: {label}: {msg}")
    return idx


if __name__ == '__main__':
    args = sys.argv[1:]
    build_all([int(args[0])] if args else None, [args[1]] if len(args) > 1 else None)
