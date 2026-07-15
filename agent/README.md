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
| `agent_diagnose.py` | Layers 1–3. `diagnose(zone_id, month)` → structured dict; `report()` prints it; writes `diagnosis_<zone>.json`. |
| `agent_explain.py` | Layer 4. `explain(diagnosis, lang)` → manager brief via `claude-opus-4-8`. English or Chinese. |
| `bn_capacity.py` | Stand-alone, detailed Theory-of-Constraints print-out for BN (the capacity logic is also inside `agent_diagnose.py`). |
| `agent_demo.ipynb` | Demo notebook with saved outputs: BN diagnosis, attribution chart, capacity chart, BN-vs-Middling comparison, and the example brief. |
| `bn_capacity_toc.png` | The BN throughput-ceiling figure. |
| `diagnosis_25559.json`, `diagnosis_25385.json` | Saved structured diagnoses (the L4 input). |

## How to run

Requires `pandas`, `numpy`, `matplotlib`, `jupyter` (and `anthropic` for L4). Data file
`cycles_all_months.csv` must be placed in the repo `data/` folder (it is git-ignored; get it
from the shared OneDrive, or rebuild it with the cycle notebooks in `notebooks/`).

```bash
# Layers 1–3: structured diagnosis + printed report
python agent_diagnose.py 25559            # BN load zone
python agent_diagnose.py 25385            # Middling (different diagnosis — same code)

# Layer 4: manager brief (needs an Anthropic API key)
export ANTHROPIC_API_KEY=sk-ant-...
python agent_explain.py 25559             # English
python agent_explain.py 25559 --lang zh   # Chinese
python agent_explain.py 25559 --dry-run   # print the prompt only, no API call
```

## Example result — BN load zone (25559, Nov 2025)

- 80.6 loads/day, 22 trucks; shovel used only ~50% → the shovel is **not** the bottleneck.
- Binding constraint is **truck idle + arrival bunching**.
- Cut idle / smooth arrivals (no new equipment): ~81 → ~131 loads/day (+62%); then roads push to
  ~160 (the shovel ceiling); expanding the shovel only pays above 160.

## Honest limits

Diagnostic, not optimiser. Recoverable numbers are **upper bounds**. November data only. No
payload data, so units are loads and truck-hours, not tonnes. A real improvement must be proven
with a **before/after pilot**, not claimed from observational data.
