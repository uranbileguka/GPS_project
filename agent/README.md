# GPS Diagnostic Agent

A manager-facing diagnostic agent for one load zone, built on GPS-derived cycle data only
(no payload / fuel / dispatch / shovel data). For a given load zone it answers: *why is the
zone slow?* and *which action helps, and in what order?*

Read [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) first — it explains the data, the idea, and
the method. This README is just how to run the code.

## Pipeline

```
cycles  →  attribution  →  decision (Theory of Constraints)  →  recommendation  →  LLM brief
 (L1)         (L2)                     (L3a/b)                       (L3c)           (L4)
```

- **L1–L3** are interpretable and need no training (point-in-polygon + percentile baselines + a
  min(supply, capacity) constraint model). No machine learning, no clustering.
- **L4** sends the structured diagnosis to a large language model and gets a short manager brief.

## Files

| File | What it is |
|---|---|
| `agent_diagnose.py` | Layers 1–3. `diagnose(zone, month=None, start=None, end=None)` → structured dict; `report()` prints it; writes `diagnosis_<zone>.json`. `zone` is a zone_id or a flow alias (`bn` / `middling` / `reject`, see `ZONE_ALIASES`). Give either `month` (a whole calendar month, e.g. `"2025-11"`) or `start`/`end` ("YYYY-MM-DD") for any date range within the data. |
| `agent_explain.py` | Layer 4. `explain(diagnosis, lang)` → manager brief via `claude-opus-4-8`. English or Chinese. `brief(zone, month=None, start=None, end=None, lang="en")` does diagnose+explain in one call — the "I say a time frame, what's wrong and what would help" entry point. |
| `bn_capacity.py` | Stand-alone, detailed Theory-of-Constraints print-out for BN (the capacity logic is also inside `agent_diagnose.py`). |
| `agent_demo.ipynb` | Demo notebook with saved outputs: BN diagnosis, attribution chart, capacity chart, BN-vs-Middling comparison, and the example brief. |
| `bn_capacity_toc.png` | The BN throughput-ceiling figure. |
| `diagnosis_25559.json`, `diagnosis_25385.json` | Saved structured diagnoses (the L4 input). |

## How to run

Requires `pandas`, `numpy`, `matplotlib`, `jupyter` (and `anthropic` for L4 — `pip install -r
../requirements.txt`). Data file `cycles_all_months.csv` resolves through `gps_lib.config.DATA_DIR`
(same `GPS_DATA_DIR` override as every other notebook in this repo — see the root README) — it's
git-ignored; get it from the shared OneDrive, or rebuild it by running
`notebooks/analysis/cycle_analysis.ipynb`'s first few cells (it caches to that file automatically).

```bash
# Layers 1–3: structured diagnosis + printed report
python agent_diagnose.py bn                                       # BN load zone, Nov 2025 (default)
python agent_diagnose.py middling                                 # different flow — different diagnosis, same code
python agent_diagnose.py bn --month 2025-07                       # a different whole month
python agent_diagnose.py bn --start 2025-11-01 --end 2025-11-15   # a specific time frame instead of a whole month
python agent_diagnose.py 25384                                    # a raw zone_id also works

# Layer 4: manager brief (needs an Anthropic API key)
export ANTHROPIC_API_KEY=sk-ant-...
python agent_explain.py bn                                        # English
python agent_explain.py bn --lang zh                              # Chinese
python agent_explain.py bn --start 2025-11-01 --end 2025-11-15    # brief for a specific time frame
python agent_explain.py bn --dry-run                              # print the prompt only, no API call
```

Or from Python, the single-call version:

```python
from agent_explain import brief
print(brief("bn", start="2025-11-01", end="2025-11-15"))   # "what's the issue, what would help"
```

## Example result — BN load zone (25559, Nov 2025)

- 80.6 loads/day, 22 trucks; shovel used only ~50% → the shovel is **not** the bottleneck.
- Two things cost loads: trucks **queue at the shovel and lose time on the road** (waste while
  actively cycling), and the fleet is **parked or off-shift** a large share of the month.
- Realistic prize (keeping today's fleet hours): cutting the queue and improving the road can
  lift 81 → about **124 loads/day (+54%)**, close to the best day already observed (109). Running
  more truck-hours (extra shifts, more available trucks) can push toward the shovel ceiling
  (~160), but that is a **separate staffing decision** — about 4,366 truck-hours a month is
  downtime, not dispatch waste. See [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) §5 for how this
  number was corrected from an earlier, inflated "+62%".

## Honest limits

Diagnostic, not optimiser. Recoverable numbers are **upper bounds**. November data only. No
payload data, so units are loads and truck-hours, not tonnes. A real improvement must be proven
with a **before/after pilot**, not claimed from observational data.
