"""The diagnosis specialist for gps_fleet_agent.ipynb — "why is throughput what it is, and
what should we do about it".

The four existing specialists answer WHAT the fleet did: cycle times, idle share, route mix,
inventory. None answers WHAT TO DO, so the notebook's own last demo question —
ask("What can be done to improve efficiency?") — falls through the router to the
human-in-the-loop node. This fills that gap.

Reads only data/agent_data/diagnosis_<zone>_<month>.json, written offline by
preprocess_v2.py. No pandas pipeline, no GPS, no import of agent_v2 — same contract as the
other fetchers, so adding it does not slow the notebook down.
"""
import json
import os
import re
from pathlib import Path
from typing import Optional

try:
    from gps_lib import config
    AGENT_DATA_DIR = Path(config.DATA_DIR) / "agent_data"
except Exception:                                  # running outside the repo
    AGENT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "agent_data"

DEFAULT_ZONE = 25559
# The three material flows, by the words a person would actually type. An unrecognised name
# used to fall through to BN, so a question about Middling came back with BN's answer and
# nothing said so.
ZONE_ALIASES = {
    "bn": 25559, "baruun": 25559, "baruun naran": 25559, "coal": 25559, "raw coal": 25559,
    "reject": 25384, "rejects": 25384, "waste": 25384, "gangue": 25384,
    "middling": 25385, "middlings": 25385, "middling coal": 25385,
}
ZONE_LABEL = {25559: "BN (raw coal, pit to plant)",
              25384: "Reject (waste rock, plant to the reject dump)",
              25385: "Middling (middlings, plant to the nearby stockpiles)"}
# Only the diagnosis specialist covers all three. preprocessing.py builds the daily/monthly
# tables for the BN sub-fleet alone, so the other four specialists cannot answer about the
# yard flows at all — saying so is better than handing back a BN number under another name.
BN_ONLY_SPECIALISTS = ("cycle_performance", "idle_analysis", "route_zone_qa", "fleet_health")

# Every message that says "I cannot answer this" carries this marker, and the caller returns
# it to the user verbatim instead of passing it to the LLM. Handed over as data context these
# do the opposite of what they say: with the diagnosis prompt asking for a ranked lever list
# and no data to rank, the model invented one ("BN: +15 loads") and, from the list of
# available files, a fabricated "one thing we cannot explain" paragraph. Plugging each entry
# point separately missed the second one, so the marker is on the messages themselves.
NO_ANSWER = '[[NO_ANSWER]]'


def is_refusal(text) -> bool:
    return isinstance(text, str) and text.startswith(NO_ANSWER)


def refusal(text: str) -> str:
    return NO_ANSWER + text


def strip_marker(text: str) -> str:
    return text[len(NO_ANSWER):] if is_refusal(text) else text


_NO_DATA_MSG = ("No diagnosis has been precomputed for that period yet. Run "
                "`python fleet_agent/preprocess_v2.py` to build it.")

# The tie rule. Measured over 30 zone-months across three material flows: every flip of the
# top lever happened while the lead was 1-4 loads/day; none of the 20 cells with a lead of 5
# or more ever flipped. A lead under 5 is reported as a tie, not as a winner.
TIE_MARGIN = 5.0


def _norm_month(month: str) -> str:
    year, mon = month.split("-")
    return f"{int(year)}-{int(mon):02d}"


class UnknownFlow(ValueError):
    """A flow name we do not recognise. Raised rather than defaulted, so a question about a
    flow this pipeline does not cover can never come back answered as BN."""


def _resolve_zone(zone) -> int:
    if zone is None:
        return DEFAULT_ZONE
    if isinstance(zone, int) or str(zone).isdigit():
        return int(zone)
    key = str(zone).strip().lower()
    if key in ZONE_ALIASES:
        return ZONE_ALIASES[key]
    raise UnknownFlow(zone)


def flows_named(text: str) -> set:
    """Zone ids whose name literally appears in the question.

    Deterministic on purpose. Asking the router to extract the flow is what failed: given
    "Which flow is worst — BN, reject or middling?" it named none of the three, the caller
    fell back to BN, and BN's answer came back as if it had compared them. Three flow words
    in the sentence and none extracted.
    """
    # Punctuation has to go first. Matching on space-padded words alone missed "for BN?" and
    # "BN, reject or middling?" — the trailing mark is part of the token — so a question about
    # another flow was answered from the selected one, which is the failure this guards.
    t = ' ' + re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip() + ' '
    return {zid for name, zid in ZONE_ALIASES.items() if f' {name} ' in t}


# Only unambiguous wordings. 'overall' and 'in total' also appear in ordinary questions
# about a single flow and were catching those.
_MINE_WIDE = ('whole mine', 'the mine', 'entire mine', 'entire fleet', 'whole fleet',
              'all flows', 'all three flows', 'across the mine', 'site-wide', 'sitewide',
              'mine-wide', 'mine wide')


def mine_wide_message(text: str, active) -> Optional[str]:
    """Refuse a mine-wide question rather than answering it from one flow.

    This started as a scope note appended to the data context. The model ignored it: asked
    what the whole mine should fix, with the note attached, it still opened with "the joint
    first priority for the whole mine to fix" — BN's figures, and BN is 22 of the site's 44
    trucks. A warning at the end of a long context does not survive a system prompt telling
    the model to lead with the verdict, so the question is refused before the model sees it.
    """
    if flows_named(text) or not any(k in str(text).lower() for k in _MINE_WIDE):
        return None
    try:
        cur = _resolve_zone(active)
    except UnknownFlow:
        return None
    return refusal(
        f"That question is mine-wide, and this specialist answers one flow at a time.\n"
        f"The site runs two separate fleets over three flows:\n{flow_menu()}\n"
        f"They haul different material over different distances, so their figures cannot be "
        f"added or ranked against each other and no single answer covers the mine.\n"
        f"The session is currently set to {ZONE_LABEL[cur]} — ask about that flow, or set "
        f"FLOW to another one.")


def wrong_flow_message(text: str, active) -> Optional[str]:
    """Set when the question is about a flow other than the one currently selected."""
    named = flows_named(text)
    try:
        cur = _resolve_zone(active)
    except UnknownFlow:
        return None                      # unknown-flow refusal handles it first
    other = named - {cur}
    if not other:
        return None
    names = ', '.join(ZONE_LABEL[z] for z in sorted(other))
    return refusal(
        f"This question names {names}, but the session is set to {ZONE_LABEL[cur]}.\n"
        f"One flow is answered at a time — they are separate fleets hauling different "
        f"material over different distances, so their figures cannot be compared or added.\n"
        f"Set FLOW to the one you want and ask again, or pass flow=... to this question.")


def flow_menu() -> str:
    return "\n".join(f"  {name}" for name in ZONE_LABEL.values())


def get_diagnosis(month: str, zone=None) -> Optional[dict]:
    path = AGENT_DATA_DIR / f"diagnosis_{_resolve_zone(zone)}_{_norm_month(month)}.json"
    return json.loads(path.read_text()) if path.exists() else None


def unknown_flow_message(zone) -> Optional[str]:
    """The refusal text if this flow name is not one we hold, else None.

    Callers must return this to the user DIRECTLY and never pass it to the LLM. Handed over
    as data context it does the opposite of what it says: the diagnosis system prompt asks
    for a ranked lever list, and with no data to rank the model invented one — "BN: +15
    loads, Reject: +10 loads", figures that exist nowhere. A refusal has to bypass the model,
    not be given to it as an instruction.
    """
    if zone is None:
        return None
    try:
        _resolve_zone(zone)
    except UnknownFlow:
        return refusal(_unknown_flow_msg(zone))
    return None


def _unknown_flow_msg(zone) -> str:
    return (f"This pipeline has no flow called \"{zone}\". It covers three:\n{flow_menu()}\n"
            f"Say which one you mean. Do NOT answer from another flow's numbers.")


def available_diagnoses() -> str:
    files = sorted(AGENT_DATA_DIR.glob("diagnosis_*_*.json"))
    if not files:
        return "  (none)"
    return "\n".join(f"  zone {p.stem.split('_')[1]}  {p.stem.split('_')[2]}" for p in files)



# Of the caveat list, only these are addressed to whoever reads the answer. The others define
# how a bucket is measured — they belong in the method write-up, and pasted into a chat answer
# they read as a wall of unexplained bullets.

def _short_cause(cause: str, width: int = 62) -> str:
    """Trim a cause to one line without cutting mid-word."""
    if len(cause) <= width:
        return cause
    cut = cause[:width].rsplit(" ", 1)[0]
    return cut + " ..."

_READER_CAVEAT_HINTS = ("UPPER BOUND", "no payload", "DIAGNOSTIC not proof")


def _caveat_blocks(caveats) -> str:
    reader = [c for c in caveats if any(h in c for h in _READER_CAVEAT_HINTS)]
    method = [c for c in caveats if c not in reader]
    out = ("STATE THESE IN THE ANSWER — one or two sentences of prose, not a bulleted list:\n"
           + "\n".join(f"  - {c}" for c in reader))
    if method:
        out += ("\n\nMETHOD NOTES — how the buckets are defined. Background for you, so that "
                "nothing you\nwrite contradicts them. Do NOT list them in the answer; mention one "
                "only if the user\nasks how something was measured:\n"
                + "\n".join(f"  - {c}" for c in method))
    return out

def _levers_block(dx: dict) -> str:
    """Split at the joint-first group. The full list runs to ten buckets ending at +0.2
    loads/day, and handed over flat it comes back as ten near-identical sentences that bury
    the one or two items the ranking can actually separate."""
    lv = dx.get("levers", [])
    if not lv:
        return "  (no levers)"
    tied = str((dx.get("lever_verdict") or {}).get("tied", "")).lower() in ("1", "true")
    head, rest = (lv[:2], lv[2:]) if tied else (lv[:1], lv[1:])
    # the unmapped-stops bucket has its own section and is barred from the recommendations;
    # leaving it in this list is what puts it back into them
    tail = [l for l in rest if not l.get("unattributed")]
    dropped = [l for l in rest if l.get("unattributed")]

    lines = ["  REPORT THESE INDIVIDUALLY:"]
    lines += [f"  {l['rank']}. {_short_cause(l['cause']):<62s} {l['bucket_truck_h']:>6.0f} "
              f"truck-h/mo   +{l['gain']:.1f} loads/day" for l in head]
    if tail:
        lines += ["",
                  f"  REPORT AS ONE GROUP — {len(tail)} further buckets, +{tail[0]['gain']:.1f} "
                  f"down to +{tail[-1]['gain']:.1f} loads/day each, "
                  f"{sum(t['bucket_truck_h'] for t in tail):.0f} truck-h/mo between them.",
                  f"  Write ONE sentence giving that count and that combined figure. Do NOT "
                  f"reproduce the list\n  below, name these buckets, or quote their individual "
                  f"gains — the gaps between them are far\n  under the {TIE_MARGIN:g} loads/day "
                  f"this ranking can resolve, so their order is not a finding.\n  Held only for "
                  f"a follow-up question that asks for them by name:"]
        lines += [f"      {l['rank']:>2d}. {_short_cause(l['cause']):<62s} "
                  f"{l['bucket_truck_h']:>5.0f} truck-h   +{l['gain']:.1f}" for l in tail]
    if dropped:
        lines += ["", f"  EXCLUDED from both groups: {_short_cause(dropped[0]['cause'])} "
                      f"({dropped[0]['bucket_truck_h']:.0f} truck-h/mo). It is real lost time and "
                      f"it stays in\n  the budget, but we cannot say what causes it, so it is "
                      f"never a recommendation. It has its\n  own section below."]
    out = "\n".join(lines)
    staff = dx.get("staffing") or []
    if isinstance(staff, dict):
        staff = [staff]
    if staff:
        out += ("\n\nNOT DISPATCH LEVERS (reported separately, never ranked against the above "
                "— a dispatcher can act on none of them):")
        for item in staff:
            out += (f"\n  {item.get('cause')}: {item.get('reservoir_truck_h', 0):.0f} truck-h/mo, "
                    f"up to +{item.get('gain', 0):.0f} loads/day.")
    return out


def _verdict_line(dx: dict) -> str:
    """The equivalent of the other fetchers' OVERALL SUMMARY line: the answer to a plain
    "what should we fix first" question, already decided, so the model does not re-rank."""
    verdict, levers = dx.get("lever_verdict", {}), dx.get("levers", [])
    if not levers:
        return "VERDICT: no lever could be ranked for this period."
    top = levers[0]
    runner = levers[1] if len(levers) > 1 else None
    margin = verdict.get("margin")
    if margin is None and runner:
        margin = round(top["gain"] - runner["gain"], 1)
    tied = str(verdict.get("tied", "")).lower() in ("1", "true") or (
        margin is not None and margin < TIE_MARGIN)
    if tied:
        names = verdict.get("top") or [top["cause"]] + ([runner["cause"]] if runner else [])
        gains = ', '.join(f"{l['cause'][:40]} +{l['gain']}" for l in levers[:2])
        return (f"VERDICT: {' and '.join(names)} are TIED for first. Their own gains are "
                f"{gains} — quote those. The {margin} loads/day between them is the GAP, not "
                f"either item's gain, and must never be reported as what they are worth; it "
                f"is under the {TIE_MARGIN:g} this ranking can resolve, which is why they are "
                f"tied. Report them together as joint first priority, each with its own "
                f"figure. Do NOT pick one over the other.")
    return (f"VERDICT: the first priority is {top['cause']} — about +{top['gain']:.1f} "
            f"loads/day, clearing the runner-up by {margin}. State it directly.")


def _gap_line(head: dict) -> str:
    """The difference between the two headline numbers, which is itself a result: how much of
    what this fleet has already achieved the named causes fail to account for."""
    u = head.get("unexplained_pct")
    if u is None:
        return ""
    if u > 0:
        return (f"+{u} points of this fleet's own best day are NOT accounted for by any cause "
                f"named above. Say so plainly — it bounds how complete this diagnosis is.")
    return ("The named causes more than cover this fleet's own best day, so nothing in its "
            "demonstrated performance is left unaccounted for.")


def _places_block(dx: dict) -> str:
    """The coordinates behind the unmapped bucket. Without these the item is unanswerable;
    with them it is one question the site can settle in a sentence."""
    pl = (dx.get("leg_decomposition") or {}).get("unmapped_places") or []
    if not pl:
        return ""
    lines = [f"    {p['truck_h']:>4} truck-h   {p['trucks']:>2} different trucks   "
             f"{p['lat']}, {p['lng']}" for p in pl[:6]]
    return ("  The biggest of those places, to be quoted verbatim so the site can identify them:\n"
            + "\n".join(lines)
            + "\n  Ask what is at these coordinates. Do not guess — three tests were run to "
              "characterise them and none separated the clusters.")


def fetch_diagnosis(month: Optional[str] = None, zone=None, default_month: str = "2025-11",
                    year: Optional[str] = None) -> str:
    """Why throughput is what it is, and what to do about it — for one month, or for a year.

    month="2025-08" answers for that month; year="2025" pools every precomputed month of that
    year (see fetch_diagnosis_year). A month wins if both are given, because it is the more
    specific request. With neither, default_month is used and the text says which month that
    was — the period is never left implicit.

    Everything the model must not get wrong is stated in the returned text rather than left
    to the prompt: the verdict is pre-decided, the headline is a range, no ceiling is quoted,
    and the scope note says these buckets partition fleet time differently from the idle
    specialist's percentages."""
    try:
        if year and not month:
            return fetch_diagnosis_year(year, zone)
        month = month or default_month
        dx = get_diagnosis(month, zone)
    except UnknownFlow:
        return refusal(_unknown_flow_msg(zone))
    if dx is None:
        return refusal(f"{_NO_DATA_MSG}\n\nPrecomputed so far:\n{available_diagnoses()}")

    thr, st = dx["throughput"], dx["stations"]
    obs, head, legs = dx["observed"], dx["headline"], dx["leg_decomposition"]
    unattributed = [l for l in dx.get("levers", []) if l.get("unattributed")]

    return f"""DIAGNOSIS — {dx['name']} ({dx['zone_id']}), {dx['month']}

{_verdict_line(dx)}

WHAT THE FLEET DID
  {thr['loads_day']} loads/day from {thr['trucks']} trucks over {thr['days']} days.
  {obs['normal_days']} normal days plus {obs['stoppage_days']} stoppage days, which cost
  {obs.get('stoppage_lost_loads', 0)} loads = {obs.get('stoppage_lost_share_pct', 0)}% of the
  month and are a separate problem from dispatch.

IS ANY STATION THE BINDING CONSTRAINT?
  shovel {st['shovel_rate']}/h at utilisation {st['rho_shovel']}; dump {st['dump_rate']}/h at {st['rho_dump']}.
  Tighter of the two: {st['binding']}. Saturated: {st['saturated']}.
  Neither is near capacity, so queueing in front of them is an ARRIVAL-TIMING problem, not a
  shortage of loading or dumping capacity. Do not recommend buying equipment on this evidence.
  No throughput ceiling is quoted deliberately: it moves between 125 and 273 loads/day across
  plausible parameter choices, so only "not saturated" survives.

WHERE THE TIME GOES
  Only {legs['driving_share_pct']}% of so-called "road" time is a truck actually driving; the
  rest is a truck standing somewhere along the route. Time is charged to where the truck was,
  not to the leg it happened during.

RANKED LEVERS (extra loads/day if the delay were removed entirely — an UPPER BOUND)
{_levers_block(dx)}

HOW MUCH IS ON THE TABLE — TWO SEPARATE MEASUREMENTS, NOT A RANGE
  +{head['day_spread_pct']}%  this fleet's own day-to-day spread: {head['day_spread_basis']}.
  +{head['explained_pct']}%  what the delays named above are worth: {head['explained_basis']}.
  These answer different questions and must never be written as "+X% to +Y%" or as a
  confidence interval. Quote each with its own basis, in its own sentence.
  {_gap_line(head)}
  Of the day-to-day spread, about {head['dispatch_share_pct']} percentage points come from each
  truck doing more trips, which is what dispatch owns; the rest is having more trucks out,
  which is maintenance.
  Do NOT add the lever gains together — each assumes the others stay as they are.

{'MEASURED BUT NOT EXPLAINED' if unattributed else ''}
{chr(10).join(f"  {l['cause']} — {l['bucket_truck_h']:.0f} truck-h. The trucks were stationary; the mine has drawn no zone there, so we cannot say what the place is. Present this as an OPEN QUESTION to put to the site, never as an action." for l in unattributed)}
{_places_block(dx) if unattributed else ''}

SCOPE NOTE — DO NOT MIX WITH THE IDLE & STOPS SPECIALIST
  This specialist and idle_analysis partition fleet time DIFFERENTLY. The idle specialist
  decides queue-versus-idle from where a truck sits relative to a zone polygon; this one
  decides it from whether another truck was already being served when this truck arrived, and
  it also accounts for stations along the road that are not in the mine's zone list. The two
  sets of percentages are not comparable and must never be added or presented as one
  breakdown. If the user quotes an idle figure from the other specialist, answer the
  what-to-do question without restating or reconciling it.

""" + _caveat_blocks(dx.get("caveats", []))



# ── Year rollup ──────────────────────────────────────────────────────────────────────
# A year is NOT a bigger month, and it is not the average of its months either. Averaging
# the monthly gains hides the one thing a year can show that a month cannot: whether the
# ranking holds. On BN 2025 it does not — the top two swap in October — so the rollup
# carries each lever's month-by-month rank next to the pooled number, and the unmapped
# stopping places are matched across months so a place that keeps coming back can be told
# apart from a one-off.

_PLACE_MATCH_M = 150      # two monthly clusters this close are treated as the same place


def year_months(year: str, zone=None) -> list:
    """Every precomputed month of that year, in order."""
    zid = _resolve_zone(zone)
    files = sorted(AGENT_DATA_DIR.glob(f"diagnosis_{zid}_{year}-*.json"))
    return [json.loads(p.read_text()) for p in files]


def _metres(a, b):
    """Flat-earth distance, good enough at this latitude over a few hundred metres. Longitude
    degrees are shorter than latitude degrees by cos(lat) — 0.72 at 43.7N — so the two axes
    cannot share one scale."""
    import math
    dlat = (a[0] - b[0]) * 111_320
    dlng = (a[1] - b[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlng)


def _merge_places(months: list) -> list:
    """Same stopping place seen in several months -> one row. DBSCAN is rerun per month, so
    the centroid of a given place moves a few tens of metres between months; matching on the
    exact coordinate would report one recurring place as five separate ones."""
    merged = []
    for dx in months:
        for p in (dx.get("leg_decomposition") or {}).get("unmapped_places") or []:
            here = (p["lat"], p["lng"])
            for m in merged:
                if _metres(here, (m["lat"], m["lng"])) <= _PLACE_MATCH_M:
                    w = m["truck_h"] + p["truck_h"]
                    if w > 0:            # a place can round to 0 truck-h on a short flow;
                        m["lat"] = (m["lat"] * m["truck_h"]      # weighting by it then
                                    + p["lat"] * p["truck_h"]) / w   # divides by zero
                        m["lng"] = (m["lng"] * m["truck_h"] + p["lng"] * p["truck_h"]) / w
                    m["truck_h"] = w
                    m["trucks"] = max(m["trucks"], p["trucks"])
                    if dx["month"][-2:] not in m["months"]:
                        m["months"].append(dx["month"][-2:])
                    break
            else:
                merged.append(dict(lat=p["lat"], lng=p["lng"], truck_h=p["truck_h"],
                                   trucks=p["trucks"], months=[dx["month"][-2:]]))
    for m in merged:
        m["lat"], m["lng"] = round(m["lat"], 5), round(m["lng"], 5)
    return sorted(merged, key=lambda m: -m["truck_h"])


def pool_year(year: str, zone=None) -> Optional[dict]:
    """Pool a year of monthly diagnoses into one ranked lever list.

    Truck-hours add across months and so do days, so the same gain formula agent_v2 uses per
    month applies unchanged to the totals: removing a bucket shortens the average cycle by
    (bucket_h / days) / loads_per_day, and throughput scales by T / (T - saving). Cycle time
    is pooled loads-weighted, not as a plain mean of the five monthly means, because the
    months carry between 13 and 26 trucks.
    """
    months = year_months(year, zone)
    if not months:
        return None
    # Compare each month's LEVER keys with each other. This used to compare lever keys with
    # buckets_truck_h keys, which held only while every bucket was also a lever. It stopped
    # holding the moment a bucket was excluded from the ranking as non-dispatch, and then no
    # flow could ever pool — including BN, which had worked the day before.
    key_sets = [set(l["key"] for l in m["levers"]) for m in months]
    if any(k != key_sets[0] for k in key_sets):
        return None       # topology differs between months; the buckets are not addable

    days = sum(m["throughput"]["days"] for m in months)
    loads_total = sum(m["throughput"]["loads_day"] * m["throughput"]["days"] for m in months)
    cyc_h = sum(m["cycle"]["cycling_truck_h_day"] * m["throughput"]["days"] for m in months)
    L = loads_total / days
    T = cyc_h * 60 / loads_total
    # ceiling, days-weighted. It has never bound on this fleet — utilisation peaks at 0.67 —
    # but the cap belongs in the formula rather than being quietly dropped.
    C = sum(min(m["stations"]["shovel_rate"], m["stations"]["dump_rate"])
            * m["throughput"]["op_hours"] * m["throughput"]["days"] for m in months) / days

    # Sum the ranked levers only. Buckets held out of the ranking (non-dispatch) have no rank
    # to collect, so reading them here raised StopIteration.
    H = {}
    for m in months:
        for l in m["levers"]:
            H[l["key"]] = H.get(l["key"], 0.0) + l["bucket_truck_h"]
    per_month_rank = {k: [next(l["rank"] for l in m["levers"] if l["key"] == k) for m in months]
                      for k in H}
    label = {l["key"]: (l["cause"], l.get("unattributed", False)) for l in months[-1]["levers"]}

    levers = []
    for k, h in H.items():
        new = min(L * T / max(T - (h / days) / L * 60, 1.0), C)
        cause, unatt = label.get(k, (k, False))
        levers.append(dict(cause=cause, key=k, bucket_truck_h=round(h),
                           new_loads=round(new, 1), gain=round(new - L, 1),
                           unattributed=unatt, ranks=per_month_rank[k]))
    levers.sort(key=lambda l: -l["gain"])
    for i, l in enumerate(levers, 1):
        l["rank"] = i

    margin = round(levers[0]["gain"] - levers[1]["gain"], 1) if len(levers) > 1 else None
    return dict(
        zone_id=months[0]["zone_id"], name=months[0]["name"], year=year,
        months=[m["month"] for m in months], days=days, loads_total=round(loads_total),
        loads_day=round(L, 1), cycle_min=round(T, 1), ceiling=round(C),
        trucks_min=min(m["throughput"]["trucks"] for m in months),
        trucks_max=max(m["throughput"]["trucks"] for m in months),
        levers=levers, places=_merge_places(months),
        lever_verdict=dict(margin=margin, tied=(margin is not None and margin < TIE_MARGIN),
                           top=[l["cause"] for l in levers[:2]]),
        per_month=[dict(month=m["month"], trucks=m["throughput"]["trucks"],
                        days=m["throughput"]["days"], loads_day=m["throughput"]["loads_day"],
                        cycle_min=m["cycle"]["cycle_min"],
                        day_spread_pct=m["headline"]["day_spread_pct"],
                        explained_pct=m["headline"]["explained_pct"],
                        rho_shovel=m["stations"]["rho_shovel"],
                        rho_dump=m["stations"]["rho_dump"],
                        saturated=m["stations"]["saturated"],
                        stoppage_days=m["observed"]["stoppage_days"],
                        top_lever=m["levers"][0]["cause"]) for m in months],
        caveats=months[-1].get("caveats", []),
    )


def _year_levers_block(yr: dict) -> str:
    rank_hdr = " ".join(m[-2:] for m in yr["months"])
    lv = yr["levers"]
    head = lv[:2] if yr["lever_verdict"]["tied"] else lv[:1]
    rest = lv[len(head):]
    tail = [l for l in rest if not l.get("unattributed")]
    dropped = [l for l in rest if l.get("unattributed")]

    lines = ["  REPORT THESE INDIVIDUALLY:"]
    if len(head) > 1:
        lines.append("  (the numbering is position in the pooled list, NOT a claim that 1 beats "
                     "2 — those two are tied)")
    for l in head:
        ranks = " ".join(f"{r:>2d}" for r in l["ranks"])
        lines.append(f"  {l['rank']:>2d}. {l['cause']}")
        lines.append(f"      {l['bucket_truck_h']:>6.0f} truck-h/yr   "
                     f"{'+%.1f' % l['gain']:>5s} loads/day   "
                     f"rank in {rank_hdr}:  {ranks}")

    if tail:
        lines.append("")
        lines.append(f"  REPORT AS ONE GROUP — {len(tail)} further buckets, "
                     f"+{tail[0]['gain']:.1f} down to +{tail[-1]['gain']:.1f} loads/day each, "
                     f"{sum(t['bucket_truck_h'] for t in tail):.0f} truck-h/yr between them.")
        lines.append("  Write ONE sentence giving that count and that combined figure. Do NOT "
                     "reproduce the list\n  below, name these buckets, or quote their individual "
                     "gains: giving each its own line\n  presents a +%.1f bucket as comparable "
                     "advice to a +%.1f one, and the gaps between them\n  are far under the %g "
                     "loads/day this ranking can resolve. Held only for a follow-up\n  question "
                     "that asks for them by name:" % (tail[-1]["gain"], head[0]["gain"], TIE_MARGIN))
        for l in tail:
            lines.append(f"      {l['rank']:>2d}. {_short_cause(l['cause']):<62s} "
                         f"{l['bucket_truck_h']:>5.0f} truck-h   {'+%.1f' % l['gain']:>5s}")
    if dropped:
        lines.append("")
        lines.append(f"  EXCLUDED from both groups: {_short_cause(dropped[0]['cause'])} "
                     f"({dropped[0]['bucket_truck_h']:.0f} truck-h/yr). Real lost time, so it "
                     f"stays in the\n  budget, but we cannot say what causes it — never a "
                     f"recommendation. Its own section is below.")

    firsts = sum(1 for r in head[0]["ranks"] if r == 1)
    lines.append("")
    lines.append(f"  The rank columns are the point of the yearly view: the leading lever held "
                 f"first place in\n  {firsts} of the {len(head[0]['ranks'])} months. Any month "
                 f"where it did not is a fact about this fleet, not noise to be\n  smoothed away "
                 f"— say so.")
    return "\n".join(lines)


def _year_places_block(yr: dict) -> str:
    pl = yr.get("places") or []
    if not pl:
        return ""
    n = len(yr["months"])
    lines = [f"    {p['truck_h']:>5.0f} truck-h   seen in {len(p['months'])} of {n} months "
             f"({'/'.join(p['months'])})   up to {p['trucks']} different trucks   "
             f"{p['lat']}, {p['lng']}" for p in pl[:6]]
    return ("  The biggest of those places, matched across months so a place that keeps coming\n"
            "  back is distinguishable from a one-off. Quote the coordinates verbatim:\n"
            + "\n".join(lines)
            + "\n  A place that recurs in most months of the year is the strongest form this\n"
              "  question takes: it is not a one-off, and the site can settle it in a sentence.\n"
              "  Ask what is there. Do not guess — three tests were run to characterise these\n"
              "  clusters and none of them separated the clusters.")


def _year_month_table(yr: dict) -> str:
    lines = [f"  {'month':<9s}{'trucks':>7s}{'days':>6s}{'loads/day':>11s}{'cycle min':>11s}"
             f"{'stoppage d':>12s}{'spread':>8s}{'explained':>11s}"]
    for m in yr["per_month"]:
        lines.append(f"  {m['month']:<9s}{m['trucks']:>7d}{m['days']:>6d}{m['loads_day']:>11.1f}"
                     f"{m['cycle_min']:>11.1f}{m['stoppage_days']:>12d}"
                     f"{'+%d%%' % m['day_spread_pct']:>8s}{'+%d%%' % m['explained_pct']:>11s}")
    return "\n".join(lines)


def fetch_diagnosis_year(year: str, zone=None) -> str:
    """The whole year as one answer: pooled levers, each lever's month-by-month rank, and the
    unmapped stopping places matched across months.

    The two headline percentages are deliberately NOT pooled. They are two different
    measurements per month and they move a lot between months; one yearly pair would read as
    a firmer number than the months support, so the table shows all five and the text says to
    quote the spread across months rather than a single figure.
    """
    try:
        yr = pool_year(year, zone)
    except UnknownFlow:
        return refusal(_unknown_flow_msg(zone))
    if yr is None:
        return refusal(
            f"No year-level diagnosis can be built for {year} on this flow. Its months do "
            f"not share one station topology, so their buckets are not the same quantity "
            f"and pooling them would add unlike things together. Ask month by month "
            f"instead.\n\nPrecomputed so far:\n{available_diagnoses()}")

    v = yr["lever_verdict"]
    top, runner = yr["levers"][0], yr["levers"][1]
    if v["tied"]:
        verdict = (f"VERDICT: over the whole of {year}, {top['cause']} and {runner['cause']} "
                   f"are TIED for first. Their own gains are +{top['gain']} and "
                   f"+{runner['gain']} — quote those. The {v['margin']} loads/day between them "
                   f"is the GAP, not either item's gain, and must never be reported as what "
                   f"they are worth; it is under the {TIE_MARGIN:g} this ranking can resolve. "
                   f"Report them together as JOINT first priority, in the opening sentence, "
                   f"each with its own figure. Do NOT pick one over the other and do not "
                   f"present the list below as if position 1 beat position 2.")
    else:
        verdict = (f"VERDICT: over the whole of {year} the first priority is {top['cause']} — "
                   f"about +{top['gain']:.1f} loads/day, clearing the runner-up by {v['margin']}.")

    sat = "yes" if any(str(m["saturated"]).lower() in ("1", "true") for m in yr["per_month"]) else "no"
    rho_lo = min(m["rho_shovel"] for m in yr["per_month"])
    rho_hi = max(m["rho_shovel"] for m in yr["per_month"])
    unatt = [l for l in yr["levers"] if l["unattributed"]]

    return f"""DIAGNOSIS — {yr['name']} ({yr['zone_id']}), FULL YEAR {yr['year']}
  Pooled from {len(yr['months'])} months: {', '.join(yr['months'])}.
  This is the whole year, not one month. Do not describe it as a monthly figure.

{verdict}

WHAT THE FLEET DID ACROSS THE YEAR
  {yr['loads_total']} loads over {yr['days']} days = {yr['loads_day']} loads/day on average,
  from {yr['trucks_min']}-{yr['trucks_max']} trucks. Average cycle {yr['cycle_min']} min.
  The monthly figures behind that average:
{_year_month_table(yr)}
  The fleet size changed by half over the year, so the yearly average is not a description of
  any single month. Quote it as an average and keep the range beside it.

IS ANY STATION THE BINDING CONSTRAINT?
  Shovel utilisation ran {rho_lo}-{rho_hi} across the {len(yr['months'])} months.
  Any month saturated: {sat}.
  Not one month came near capacity, so queueing in front of a station is an ARRIVAL-TIMING
  problem, not a shortage of loading or dumping capacity. This is the single conclusion that
  has survived every correction to the method — it is the safest thing in this report. Do not
  recommend buying equipment on this evidence. No throughput ceiling is quoted: it moves
  between 125 and 273 loads/day under plausible parameter choices.

RANKED LEVERS FOR THE YEAR (extra loads/day if the delay were removed entirely — UPPER BOUND)
{_year_levers_block(yr)}

  Truck-hours are yearly totals; the loads/day figure is what removing that bucket would be
  worth against the yearly average, each one assuming every other delay stays exactly as it
  is. So the two joint-first levers are NOT worth the sum of their two numbers. Adding them
  is wrong. Quote {top['gain']:+.1f} and {runner['gain']:+.1f} separately, never their total.

HOW MUCH IS ON THE TABLE — PER MONTH, NOT POOLED
  Both percentages are in the table above. They are two different measurements — the fleet's
  own day-to-day spread, and what the named delays are worth — and they must never be written
  as a range or a confidence interval, nor averaged into one yearly pair. Quote the range
  across months, each with its own basis, and say that they move.

{'MEASURED BUT NOT EXPLAINED' if unatt else ''}
{chr(10).join(f"  {l['cause']} — {l['bucket_truck_h']:.0f} truck-h across the year. The trucks were stationary; the mine has drawn no zone there, so we cannot say what the place is. Present this as an OPEN QUESTION to put to the site, never as an action." for l in unatt)}
{_year_places_block(yr) if unatt else ''}

SCOPE NOTE — DO NOT MIX WITH THE IDLE & STOPS SPECIALIST
  This specialist and idle_analysis partition fleet time DIFFERENTLY, so their percentages
  are not comparable and must never be added or presented as one breakdown.

""" + _caveat_blocks(yr.get("caveats", [])) + f"""
  - Pooling assumes the buckets mean the same thing in every month. All {len(yr['months'])}
    months were checked to carry the same {len(yr['levers'])} buckets; if a future month
    discovers a different station topology the rollup refuses to build rather than adding
    unlike things together."""


# ── Router / specialist wiring, imported by the notebook ──────────────────────────────
DIAGNOSIS_INTENT = "diagnosis"

ROUTER_INTENT_LINE = (
    "- diagnosis: why throughput is what it is, what is causing lost time, what to do about "
    "it, what to fix first, how much could be gained, whether the shovel is the bottleneck, "
    "whether to add trucks or equipment"
)

DIAGNOSIS_PROMPT = (
    "You are the Diagnosis & Recommendations agent for a mine haul fleet. The data below has "
    "a VERDICT line — that ranking is already decided from the measurements; state it "
    "directly and do not re-rank from the lever table yourself. If it says the top items are "
    "tied, report them together and do not pick one. Never quote a throughput ceiling. "
    "Never sum the lever gains. "
    "OPENING: your first sentence states the VERDICT line's conclusion — which lever is "
    "first, or which are tied for first. Do not open with a bare numbered list. "
    "LENGTH — THIS RULE GOVERNS THE LEVER LIST ONLY, nothing else in the answer: name "
    "ONLY the levers the data block lists under REPORT THESE INDIVIDUALLY. Everything "
    "under REPORT AS ONE GROUP gets a single sentence between them, giving the count "
    "and the combined truck-hours, and no per-item bullet, gain figure, or sentence of "
    "its own. A ten-item list where every line is the same sentence with a different "
    "number buries the items that matter, and the small ones are below what this "
    "method can resolve anyway. This brevity rule does NOT apply to the "
    "cannot-explain paragraph or to the caveats: both must appear in full however "
    "short the rest of the answer is. "
    "NEVER ADD TWO GAINS TOGETHER. Each gain assumes every other delay stays exactly "
    "as it is, so two tied levers worth +A and +B are NOT worth +(A+B) — writing that "
    "sum is the single worst error you can make with this data. Quote each figure "
    "separately, or give neither. "
    "Anything under MEASURED BUT NOT EXPLAINED must NOT appear in your list of "
    "recommendations at all. Give it its own closing paragraph headed 'One thing we "
    "cannot explain', state the truck-hours, and quote the coordinates and truck counts "
    "verbatim as a question for the site to answer. Listing it as something to fix would "
    "be inventing a cause we do not have. "
    "Obey the SCOPE NOTE: do not add or compare these figures to the idle specialist's. Carry "
    "the STATE THESE IN THE ANSWER caveats into your closing — as one or two sentences of "
    "prose, never as a bulleted list, and never the METHOD NOTES. The points that must "
    "land: this is a diagnosis rather than proof, the gains are upper bounds, and only a "
    "before/after pilot turns a recoverable figure into a real one. There is no payload "
    "data, so speak in loads and truck-hours, never tonnes."
)
