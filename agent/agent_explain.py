#!/usr/bin/env python3
"""
L4 — LLM explanation layer.  Turns a structured diagnosis (from agent_diagnose.py)
into a manager-facing narrative: WHY the zone is slow + WHICH lever, honestly framed.

Grounded strictly in the diagnosis JSON — the model is told to invent nothing.

Usage:
    python agent_explain.py bn                              # English brief, Nov 2025 (needs OPENAI_API_KEY)
    python agent_explain.py bn --lang zh                     # Chinese brief
    python agent_explain.py bn --start 2025-11-01 --end 2025-11-15   # a specific time frame instead of a whole month
    python agent_explain.py bn --dry-run                     # print the prompt only, no API call
    python agent_explain.py middling                         # same code, different flow -> different diagnosis

Requires: pip install openai ; and OPENAI_API_KEY in the environment / .env.
"""
import json, sys, argparse
from agent_diagnose import diagnose, resolve_zone

MODEL = "gpt-4o"

SYSTEM = """You are a mining haulage operations analyst writing a short briefing for the \
pit manager of an open-pit coal mine (Baruun Naran circuit, South Gobi, Mongolia). You are \
given a STRUCTURED DIAGNOSIS produced by a GPS-only analytics pipeline for one load zone. \
Turn it into a clear, decision-focused brief.

Rules:
- Use ONLY the numbers and facts in the diagnosis. Never invent figures, causes, or levers \
that are not present. If something is not in the data, do not claim it.
- Lead with the single most important finding: what is slowing this zone, and whether the \
shovel (loader) is the bottleneck.
- Explain the binding constraint in plain language a manager without an analytics background \
understands (e.g. "trucks stand idle and arrive in convoys" rather than "supply-bound").
- Give the recommendations in priority order. For each: the lever, the expected throughput \
effect (quote the actual numbers), and its prerequisite or caveat. Make clear that later \
levers only pay off after earlier ones, and that some are capped by the shovel ceiling.
- Preserve the honesty frame explicitly, in the manager's words: this is a DIAGNOSTIC, not a \
guarantee; the recoverable figures are UPPER BOUNDS; a real gain must be proven with a \
before/after pilot; there is no payload data, so units are loads and truck-hours, not tonnes.
- Be concrete and brief (about 350-500 words). No preamble like "Here is". Use short \
paragraphs and/or bullets with clear headers."""

LANG = {"en": "Write the brief in clear English.",
        "zh": "Write the brief in simplified Chinese."}


def build_prompt(dx, lang="en"):
    user = (
        "Here is the structured diagnosis for one load zone (JSON). "
        "Write the pit-manager brief per your rules. " + LANG.get(lang, LANG["en"]) +
        "\n\n```json\n" + json.dumps(dx, ensure_ascii=False, indent=2) + "\n```"
    )
    return SYSTEM, user


def explain(dx, lang="en", model=MODEL):
    from openai import OpenAI
    system, user = build_prompt(dx, lang)
    client = OpenAI()                                     # resolves OPENAI_API_KEY from the environment
    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content


def brief(zone, month=None, start=None, end=None, lang="en", model=MODEL):
    """One call from "zone + time frame" straight to the manager narrative:
    runs L1-L3 (diagnose) then L4 (explain). `zone` is a zone_id or a friendly
    name ('bn' / 'middling' / 'reject'); give either `month` (a whole
    calendar month) or `start`/`end` (any date range within Jul-Nov 2025).
    """
    dx = diagnose(resolve_zone(zone), month=month, start=start, end=end)
    return explain(dx, lang=lang, model=model)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Layer 4: zone + time frame -> manager-facing brief.")
    ap.add_argument("zone", nargs="?", default="bn", help="zone_id or flow name: bn / middling / reject")
    ap.add_argument("--month", default=None, help="e.g. 2025-11 (default if no --start/--end given)")
    ap.add_argument("--start", default=None, help="e.g. 2025-11-01 (with --end, overrides --month)")
    ap.add_argument("--end", default=None, help="e.g. 2025-11-15 (inclusive)")
    ap.add_argument("--lang", default="en", choices=["en", "zh"])
    ap.add_argument("--dry-run", action="store_true", help="print the prompt, do not call the API")
    a = ap.parse_args()

    dx = diagnose(resolve_zone(a.zone), month=a.month, start=a.start, end=a.end)
    system, user = build_prompt(dx, a.lang)
    if a.dry_run:
        print("=== SYSTEM ===\n" + system + "\n\n=== USER ===\n" + user)
        sys.exit(0)
    try:
        print(explain(dx, a.lang))
    except Exception as e:
        print(f"[LLM call failed: {type(e).__name__}: {e}]\n"
              f"Set OPENAI_API_KEY in the environment or .env and retry, "
              f"or use --dry-run to inspect the prompt.", file=sys.stderr)
        sys.exit(1)
