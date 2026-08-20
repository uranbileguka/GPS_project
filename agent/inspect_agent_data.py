"""Print the head of every CSV under data/agent_data/ — a quick sanity check
after running fleet_agent/preprocessing.py. Run directly:

    python agent/inspect_agent_data.py
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd

from gps_lib import config

AGENT_DATA_DIR = Path(config.DATA_DIR) / "agent_data"
N_ROWS = 5


def main() -> None:
    if not AGENT_DATA_DIR.exists():
        print(f"{AGENT_DATA_DIR} doesn't exist yet — run `python fleet_agent/preprocessing.py` first.")
        return

    files = sorted(AGENT_DATA_DIR.glob("*.csv"))
    if not files:
        print(f"No CSVs found in {AGENT_DATA_DIR} yet — run `python fleet_agent/preprocessing.py` first.")
        return

    for f in files:
        df = pd.read_csv(f, dtype={"tracker_id": str})
        print(f"=== {f.name} — {df.shape[0]} rows x {df.shape[1]} cols ===")
        print(df.head(N_ROWS).to_string(index=False))
        print()


if __name__ == "__main__":
    main()
