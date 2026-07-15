#!/usr/bin/env python3
"""
L4 — LLM explanation layer.  Turns a structured diagnosis (from agent_diagnose.py)
into a manager-facing narrative: WHY the zone is slow + WHICH lever, honestly framed.

Grounded strictly in the diagnosis JSON — the model is told to invent nothing.

Usage:
    python analysis/agent_explain.py 25559                # English brief (needs ANTHROPIC_API_KEY)
    python analysis/agent_explain.py 25559 --lang zh      # Chinese brief
    python analysis/agent_explain.py 25559 --dry-run      # print the prompt only, no API call

Requires: pip install anthropic ; and ANTHROPIC_API_KEY (or `ant auth login`).
"""
import json, sys, argparse
from agent_diagnose import diagnose

MODEL = "claude-opus-4-8"

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
    import anthropic
    system, user = build_prompt(dx, lang)
    client = anthropic.Anthropic()                       # resolves ANTHROPIC_API_KEY / ant profile
    with client.messages.stream(
        model=model, max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("zone_id", type=int, nargs="?", default=25559)
    ap.add_argument("--month", default="2025-11")
    ap.add_argument("--lang", default="en", choices=["en", "zh"])
    ap.add_argument("--dry-run", action="store_true", help="print the prompt, do not call the API")
    a = ap.parse_args()

    dx = diagnose(a.zone_id, a.month)
    system, user = build_prompt(dx, a.lang)
    if a.dry_run:
        print("=== SYSTEM ===\n" + system + "\n\n=== USER ===\n" + user)
        sys.exit(0)
    try:
        print(explain(dx, a.lang))
    except Exception as e:
        print(f"[LLM call failed: {type(e).__name__}: {e}]\n"
              f"Set ANTHROPIC_API_KEY (or run `ant auth login`) and retry, "
              f"or use --dry-run to inspect the prompt.", file=sys.stderr)
        sys.exit(1)
