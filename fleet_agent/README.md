# fleet_agent

Everything needed to run the GPS Fleet Ops Agent, and nothing else. `agent/` next door
holds the method write-up, its figures, and earlier scripts — none of that is imported here.

## Files

| File | What it is |
|---|---|
| `gps_fleet_agent.ipynb` | The agent. Router + five specialists, built on LangGraph. Start here. |
| `agent_v2_specialist.py` | The diagnosis specialist the notebook imports. Reads a JSON, nothing else. |
| `agent_v2.py` | The diagnosis engine: builds the trip table, spreads pings over the discovered stations, ranks the levers. Not imported at chat time. |
| `preprocess_v2.py` | Runs `agent_v2.diagnose_v2` offline and writes one JSON per zone-month. |
| `preprocessing.py` | Builds the daily / monthly / route / zone-QA tables the other four specialists read. |

`gps_lib/` at the repo root is **shared with the rest of the project and is deliberately not
copied in here**. `gps_lib/cycles.py` in particular is called by both `preprocessing.py` and
`agent_v2.py`; it was duplicated once before, the two copies drifted, and the same three
defects had to be fixed twice. One copy, both callers.

## Setup

```bash
pip install -r ../requirements.txt
```

Three of those pins matter and are easy to lose:

- **`Brotli >= 1.2`** — 1.0.9 makes every OpenAI request fail with `APIConnectionError`. Its
  `process()` rejects keyword arguments and the `openai` client calls it that way.
- **`aiohttp >= 3.10`** — 3.9.5 has no `SocketTimeoutError`, so `langchain_openai` fails on import.
- `langgraph`, `langchain-openai`.

Then a `.env` at the repo root (copy `.env.example`):

```
GPS_DATA_DIR=/path/to/data      # where the raw gps_data_<year>-<month>.csv files live
OPENAI_API_KEY=sk-...
```

## Running it

Two offline builds first. They read raw GPS and write small files under
`$GPS_DATA_DIR/agent_data/`; the notebook only ever reads those.

```bash
python fleet_agent/preprocessing.py                     # daily_*, monthly_*, routes_*, zone_qa_*
python fleet_agent/preprocess_v2.py                     # diagnosis_<zone>_<month>.json
python fleet_agent/preprocess_v2.py 25559 2025-11       # or just one zone-month
```

`preprocess_v2.py` takes about 30 seconds per month the first time and caches the trip table
and the pings under `fleet_agent/.cycle_cache/` and `.ping_cache/` (gitignored, ~250 MB).
That is why the diagnosis is precomputed rather than run inside a chat turn.

Then open `gps_fleet_agent.ipynb` and run it top to bottom.

```python
ask("What can be done to improve efficiency?")                    # defaults to MONTH
ask("What should we fix first?",            month="2025-08")      # one month
ask("What can be done to improve efficiency?", year="2025")       # the year, pooled
```

Give both `month` and `year` and the month wins. A year pools every month of that year that
has been precomputed, and additionally reports where each lever ranked in each month — the
ranking is not stable across months and the yearly view is where that shows.

Scope: BN only. The other two material flows haul 0.4 km and 2 km, where the road and station
layers have nothing to measure.
