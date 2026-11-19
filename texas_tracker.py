#!/usr/bin/env python3
"""Texas data center pipeline tracker.

    python texas_tracker.py --status
    python texas_tracker.py --transitions
    python texas_tracker.py --calendar
    python texas_tracker.py --bills
    python texas_tracker.py --set-stage "Project name" batch_zero --source "URL"
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
PROJECTS_FILE = DATA / "projects.json"
HISTORY_FILE = DATA / "stage_history.json"

STAGES = [
    ("announced",        "Announced",             "Press release only. No regulatory meaning."),
    ("site_control",     "Site control",          "Land secured. Weak gate in Texas (limited county zoning)."),
    ("env_permit",       "Environmental permit",  "TCEQ. Became a gate 2026-09-21 when Abbott extended the pause here."),
    ("request_filed",    "Interconnection filed", "In ERCOT queue. 75 MW threshold, PURA 37.0561."),
    ("batch_zero",       "Batch Zero screening",  "Front-end screening, financial security, disclosure."),
    ("study_complete",   "Batch study complete",  "The real technical gate."),
    ("approved",         "Approval to Energize",  "ERCOT clearance to connect."),
    ("energized",        "Energized / ramping",   "Drawing power."),
    ("paused",           "Paused / delayed",      "Construction or process halted."),
    ("cancelled",        "Cancelled",             "Dead."),
]

STAGE_INDEX = {key: i for i, (key, _, _) in enumerate(STAGES)}
STAGE_LABEL = {key: label for key, label, _ in STAGES}

OFF_RAMP = {"paused", "cancelled"}

CALENDAR = [
    ("2026-12-10", "ERCOT VERIFICATION REPORT due to PUCT (not an approvals list)",
     "Report on which projects are verified/eligible. PUCT then acts on it, "
     "then Batch Zero studies resume, then approvals follow. Unblocks the "
     "process; does not conclude it.",
     "Abbott letter 2026-08-03; ERCOT Batch Zero update Sept 2026"),
    ("2026-12-31", "PUCT final SB 6 large-load rule deadline",
     "Sets curtailment obligations for 75 MW+ loads.",
     "SB 6 (2025) / 16 TAC 25.194"),
    ("2027-01-12", "Texas Legislature convenes (regular session)",
     "First window for statutory moratorium or cost-allocation change. "
     "Date is the statutory second Tuesday in January; verify exact date.",
     "Texas Constitution Art. 3 Sec. 5"),
    ("2027-01-19", "Governor-elect Hinojosa inauguration (approximate)",
     "PUCT appointments begin flowing over subsequent terms. Verify exact date.",
     "Election result, 2026-11-03"),
]

SEED_PROJECTS = {
    "Stargate / Abilene": {
        "operator": "Lancium Clean Campus / OpenAI-linked",
        "county": "Taylor",
        "capacity_mw": 1200,
        "stage": "energized",
        "as_of": "2026-07-01",
        "source": "Epoch AI buildout tracking",
        "notes": "Crossed 1 GW facility power July 2026. Two buildings live "
                 "since Sept 2025, six ramping.",
    },
    "Vantage Frontier Campus": {
        "operator": "Vantage Data Centers",
        "county": "Shackelford / Taylor",
        "capacity_mw": 1400,
        "stage": "site_control",
        "as_of": "2026-07-01",
        "source": "interconnectionqueue.org",
        "notes": "Under construction, first building targeted H2 2026.",
    },
    "Project Matador": {
        "operator": "Fermi America",
        "county": "Potter / Randall",
        "capacity_mw": 11000,
        "stage": "paused",
        "as_of": "2026-01-01",
        "source": "interconnectionqueue.org",
        "notes": "Construction paused early 2026. The cautionary case: an "
                 "11 GW announcement that became a pause.",
    },
}

GENERATION = {
    "NRG Cedar Bayou 5": {
        "company": "NRG Energy", "capacity_mw": 721,
        "award": "$562M loan, 20yr @ 3%", "status": "awarded",
        "online": "2028", "zone": "Houston",
    },
    "NRG T.H. Wharton": {
        "company": "NRG Energy", "capacity_mw": 456,
        "award": "up to $216M", "status": "awarded",
        "online": "2028", "zone": "Houston",
    },
    "NRG Greens Bayou": {
        "company": "NRG Energy", "capacity_mw": 455,
        "award": "TxEF loan", "status": "awarded",
        "online": "2028", "zone": "Houston",
    },
    "Constellation (unnamed)": {
        "company": "Constellation Energy Generation", "capacity_mw": 460,
        "award": "$278M", "status": "awarded",
        "online": "TBD", "zone": "TBD",
    },
    "Rayburn Energy Station 2": {
        "company": "Rayburn Electric Cooperative", "capacity_mw": 570,
        "award": "$411M", "status": "awarded",
        "online": "2028", "zone": "North",
    },
    "LCRA Timmerman Unit 1": {
        "company": "LCRA", "capacity_mw": 188,
        "award": "up to $22.56M completion bonus grant", "status": "awarded",
        "online": "operating", "zone": "South",
    },
    "CPV Basin Ranch": {
        "company": "Competitive Power Ventures", "capacity_mw": 1350,
        "award": "not TxEF", "status": "announced",
        "online": "TBD", "zone": "West (Ward County)",
    },
    "Reeves County plant": {
        "company": "(see Oct 7 2026 Governor release)", "capacity_mw": 452,
        "award": "TxEF loan #9", "status": "awarded",
        "online": "2027", "zone": "West",
    },
}

AGGREGATE = {
    "as_of": "2026-06-30",
    "requests_gw": 474.7,
    "datacenter_gw": 420.8,
    "datacenter_share": 0.902,
    "batch_zero_conditional_gw": 194.3,
    "approval_to_energize_gw": 9.0,
    "observed_peak_large_load_gw": 3.9,
    "ercot_record_peak_gw": 85.5,
    "source": "ERCOT testimony to Texas Senate 2026-07-29; Abbott letter 2026-08-03",
}


def ensure_data_dir() -> None:
    DATA.mkdir(parents=True, exist_ok=True)


def load_projects() -> dict:
    ensure_data_dir()
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text(json.dumps(SEED_PROJECTS, indent=2))
        print(f"Initialised {PROJECTS_FILE} with seed data.\n", file=sys.stderr)
    return json.loads(PROJECTS_FILE.read_text())


def save_projects(projects: dict) -> None:
    ensure_data_dir()
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2, sort_keys=True))


def load_history() -> list:
    ensure_data_dir()
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text())


def append_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def cmd_status() -> int:
    projects = load_projects()
    agg = AGGREGATE

    funnel = (agg["observed_peak_large_load_gw"] / agg["requests_gw"]) * 100

    print("ERCOT LARGE-LOAD PIPELINE")
    print(f"  as of {agg['as_of']}\n")
    print(f"  Requests filed          {agg['requests_gw']:>8.1f} GW")
    print(f"    of which data centers {agg['datacenter_gw']:>8.1f} GW  "
          f"({agg['datacenter_share']*100:.1f}%)")
    print(f"  Batch Zero conditional  {agg['batch_zero_conditional_gw']:>8.1f} GW")
    print(f"  Approval to Energize    {agg['approval_to_energize_gw']:>8.1f} GW")
    print(f"  Observed peak draw      {agg['observed_peak_large_load_gw']:>8.1f} GW")
    print(f"  ERCOT record peak       {agg['ercot_record_peak_gw']:>8.1f} GW")
    print()
    print(f"  Request-to-operating conversion: {funnel:.2f}%")
    print(f"  Queue is {agg['requests_gw']/agg['ercot_record_peak_gw']:.1f}x the grid's record peak.")
    print()
    print("  Read the queue total as a measure of interest, never of capacity.")
    print(f"  Source: {agg['source']}")

    print("\n" + "=" * 68)
    print("TRACKED PROJECTS\n")

    def sort_key(item):
        stage = item[1]["stage"]
        return (stage in OFF_RAMP, -STAGE_INDEX.get(stage, 0))

    for name, p in sorted(projects.items(), key=sort_key):
        label = STAGE_LABEL.get(p["stage"], p["stage"])
        print(f"  {name}")
        print(f"    {label:<24} {p['capacity_mw']:>6,} MW   {p['county']} County")
        print(f"    operator: {p['operator']}")
        print(f"    as of {p['as_of']}  |  source: {p['source']}")
        if p.get("notes"):
            print(f"    {p['notes']}")
        print()

    return 0


def cmd_transitions(days: int) -> int:
    history = load_history()
    cutoff = dt.date.today() - dt.timedelta(days=days)

    recent = [
        h for h in history
        if dt.date.fromisoformat(h["recorded"][:10]) >= cutoff
    ]

    print(f"STAGE TRANSITIONS (last {days} days)\n")

    if not recent:
        print("  No recorded transitions in the window.")
        print("\n  This is a real finding, not a gap: the energization pause")
        print("  means the pipeline is largely frozen pending the Dec 10 reports.")
        return 0

    for h in sorted(recent, key=lambda x: x["recorded"], reverse=True):
        old = STAGE_LABEL.get(h["from"], h["from"])
        new = STAGE_LABEL.get(h["to"], h["to"])
        if h["to"] in OFF_RAMP:
            direction = "HALT"
        elif h["from"] in OFF_RAMP:
            direction = "RESUME"
        elif h.get("advanced"):
            direction = "ADVANCE"
        else:
            direction = "REGRESS"
        print(f"  [{direction}] {h['project']}")
        print(f"    {old} -> {new}")
        print(f"    recorded {h['recorded'][:10]}  |  source: {h.get('source','(none)')}")
        print()

    return 0


def cmd_calendar(horizon_days: int) -> int:
    today = dt.date.today()
    cutoff = today + dt.timedelta(days=horizon_days)

    print(f"REGULATORY CALENDAR (next {horizon_days} days)\n")

    upcoming = [
        (dt.date.fromisoformat(d), what, why, src)
        for d, what, why, src in CALENDAR
        if today <= dt.date.fromisoformat(d) <= cutoff
    ]

    if not upcoming:
        print("  Nothing scheduled in the window.")
        return 0

    for date, what, why, src in sorted(upcoming):
        days = (date - today).days
        print(f"  {date.isoformat()}  ({days} days away)")
        print(f"    {what}")
        print(f"    {why}")
        print(f"    source: {src}")
        print()

    print("  These are calendar facts. Report the date, not a forecast of")
    print("  what it will contain.")
    return 0


def cmd_bills(session: str) -> int:
    print("TEXAS LEGISLATURE BILL SEARCH\n")
    print(f"  Session: {session}")
    print()
    print("  Texas Legislature Online has no public API and its search is")
    print("  form-driven. A scraper here breaks quietly, which is worse than")
    print("  no scraper. Check these directly:\n")

    terms = [
        "data center",
        "large load",
        "ERCOT cost allocation",
        "interconnection",
        "curtailment",
    ]
    for t in terms:
        print(f"    - \"{t}\"")

    print()
    print("  Search at: https://capitol.texas.gov/Search/BillSearch.aspx")
    print("  PUCT filings: https://interchange.puc.texas.gov  (Project 58481)")
    print()
    print("  The Texas Legislature meets in regular session only in")
    print("  odd-numbered years. Nothing can pass between sessions, so bill")
    print("  activity before January 2027 is pre-filing only.")
    return 0


def cmd_generation() -> int:
    print("TEXAS ENERGY FUND / DISPATCHABLE GENERATION\n")
    print("  Dispatchable = operator can turn it up or down on command")
    print("  (gas, coal, nuclear, hydro, batteries). Not wind or solar.")
    print("  These are permanent plants, not rental or bridge power.\n")

    awarded = {k: v for k, v in GENERATION.items() if v["status"] == "awarded"}
    other = {k: v for k, v in GENERATION.items() if v["status"] != "awarded"}

    total = sum(v["capacity_mw"] for v in awarded.values())

    print(f"  TxEF-awarded tracked here: {total:,} MW across {len(awarded)} projects")
    print("  (9 In-ERCOT loans finalised statewide as of Oct 2026, >5,400 MW)\n")

    for label, group in (("AWARDED", awarded), ("OTHER", other)):
        if not group:
            continue
        print(f"  {label}")
        for name, g in sorted(group.items(), key=lambda x: -x[1]["capacity_mw"]):
            print(f"    {name}")
            print(f"      {g['capacity_mw']:>6,} MW  {g['company']}")
            print(f"      {g['award']}  |  online {g['online']}  |  {g['zone']} zone")
        print()

    print("  WATCH WITHDRAWALS, NOT JUST AWARDS.")
    print("  Six of the initial 17 TxEF projects withdrew voluntarily, citing")
    print("  rising costs, equipment procurement constraints and")
    print("  lower-than-expected returns. Nobody announces a withdrawal, which")
    print("  is why it is the cleaner signal about merchant gas economics.")
    print()
    print("  Source: PUCT Texas Energy Fund program pages and Governor's")
    print("  office releases. Verify at puc.texas.gov before citing.")
    return 0


def snapshot() -> dict:
    today = dt.date.today()
    projects = load_projects()
    agg = AGGREGATE
    cal = []
    for d, what, why, src in CALENDAR:
        dd = dt.date.fromisoformat(d)
        cal.append({"date": d, "days_away": (dd - today).days, "what": what,
                    "why": why, "source": src})
    cal.sort(key=lambda e: e["date"])
    stages = [{"key": k, "label": lbl, "desc": desc, "off_ramp": k in OFF_RAMP}
              for k, lbl, desc in STAGES]
    projs = []
    for name, p in projects.items():
        projs.append({"name": name, "stage": p["stage"],
                      "stage_label": STAGE_LABEL.get(p["stage"], p["stage"]),
                      "stage_index": STAGE_INDEX.get(p["stage"], 0),
                      "off_ramp": p["stage"] in OFF_RAMP,
                      "operator": p.get("operator", ""), "county": p.get("county", ""),
                      "capacity_mw": p.get("capacity_mw", 0), "as_of": p.get("as_of", ""),
                      "source": p.get("source", ""), "notes": p.get("notes", "")})
    projs.sort(key=lambda x: (x["off_ramp"], -x["stage_index"], -x["capacity_mw"]))
    gen = [{"name": n, **g} for n, g in GENERATION.items()]
    gen.sort(key=lambda g: (g["status"] != "awarded", -g["capacity_mw"]))
    cutoff = today - dt.timedelta(days=90)
    trans = [h for h in load_history()
             if dt.date.fromisoformat(h["recorded"][:10]) >= cutoff]
    for h in trans:
        h["from_label"] = STAGE_LABEL.get(h["from"], h["from"])
        h["to_label"] = STAGE_LABEL.get(h["to"], h["to"])
        h["kind"] = ("halt" if h["to"] in OFF_RAMP else "resume" if h["from"] in OFF_RAMP
                     else "advance" if h.get("advanced") else "regress")
    return {
        "aggregate": {**agg,
                      "conversion_pct": round(agg["observed_peak_large_load_gw"] / agg["requests_gw"] * 100, 2),
                      "queue_vs_peak": round(agg["requests_gw"] / agg["ercot_record_peak_gw"], 1)},
        "stages": stages, "projects": projs, "generation": gen, "calendar": cal,
        "transitions": sorted(trans, key=lambda h: h["recorded"], reverse=True),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def cmd_set_stage(name: str, stage: str, source: str) -> int:
    if stage not in STAGE_INDEX:
        print(f"Unknown stage '{stage}'. Valid stages:\n", file=sys.stderr)
        for key, label, desc in STAGES:
            print(f"  {key:<16} {label:<24} {desc}", file=sys.stderr)
        return 1

    projects = load_projects()

    if name not in projects:
        print(f"Unknown project '{name}'. Tracked projects:", file=sys.stderr)
        for p in projects:
            print(f"  {p}", file=sys.stderr)
        return 1

    old_stage = projects[name]["stage"]
    if old_stage == stage:
        print(f"{name} is already at stage '{stage}'. Nothing recorded.")
        return 0

    old_off = old_stage in OFF_RAMP
    new_off = stage in OFF_RAMP

    if new_off:
        advanced = False
    elif old_off:
        advanced = True
    else:
        advanced = STAGE_INDEX[stage] > STAGE_INDEX[old_stage]

    projects[name]["stage"] = stage
    projects[name]["as_of"] = dt.date.today().isoformat()
    projects[name]["source"] = source
    save_projects(projects)

    append_history({
        "project": name,
        "from": old_stage,
        "to": stage,
        "advanced": advanced,
        "recorded": dt.datetime.now().isoformat(timespec="seconds"),
        "source": source,
    })

    arrow = "advanced to" if advanced else "moved to"
    print(f"{name}: {STAGE_LABEL[old_stage]} -> {STAGE_LABEL[stage]} ({arrow})")
    print(f"Recorded with source: {source}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true",
                        help="current pipeline snapshot and tracked projects")
    parser.add_argument("--transitions", action="store_true",
                        help="stage changes recorded recently")
    parser.add_argument("--calendar", action="store_true",
                        help="upcoming regulatory dates")
    parser.add_argument("--bills", action="store_true",
                        help="legislature search guidance")
    parser.add_argument("--generation", action="store_true",
                        help="Texas Energy Fund dispatchable generation pipeline")
    parser.add_argument("--json", action="store_true",
                        help="everything as JSON, for the web page")
    parser.add_argument("--set-stage", nargs=2, metavar=("PROJECT", "STAGE"),
                        help="record a stage change (requires --source)")
    parser.add_argument("--source", default="",
                        help="primary source URL or citation for a stage change")
    parser.add_argument("--days", type=int, default=30,
                        help="lookback for --transitions (default 30)")
    parser.add_argument("--horizon", type=int, default=120,
                        help="lookahead for --calendar (default 120)")
    parser.add_argument("--session", default="90R",
                        help="legislature session for --bills (default 90R)")
    args = parser.parse_args()

    if args.set_stage:
        if not args.source:
            print("--set-stage requires --source. A stage change without a "
                  "primary source is a guess, and a wrong stage is worse than "
                  "a missing one.", file=sys.stderr)
            return 1
        return cmd_set_stage(args.set_stage[0], args.set_stage[1], args.source)

    if args.json:
        import json as _json
        print(_json.dumps(snapshot(), indent=1))
        return 0
    if args.transitions:
        return cmd_transitions(args.days)
    if args.calendar:
        return cmd_calendar(args.horizon)
    if args.bills:
        return cmd_bills(args.session)
    if args.generation:
        return cmd_generation()

    return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
