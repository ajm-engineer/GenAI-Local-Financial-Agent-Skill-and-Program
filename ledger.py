#!/usr/bin/env python3
"""Hypothesis ledger: records falsifiable claims and scores them.

    python ledger.py --add
    python ledger.py --open
    python ledger.py --due
    python ledger.py --resolve ID true
    python ledger.py --score
    python ledger.py --export
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
import uuid
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "ledger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS hypotheses (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    claim         TEXT NOT NULL,
    subject       TEXT,
    category      TEXT NOT NULL,
    mechanism     TEXT,
    confidence    REAL NOT NULL,
    resolve_by    TEXT NOT NULL,
    evidence      TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    outcome       INTEGER,
    resolved_at   TEXT,
    resolution_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_resolve ON hypotheses(resolve_by);

-- One row per (claim, panel member). See panel.py. The first forecast a
-- member makes on a claim stands; there is deliberately no update path.
CREATE TABLE IF NOT EXISTS forecasts (
    claim_id    TEXT NOT NULL,
    member      TEXT NOT NULL,
    prob        REAL NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (claim_id, member)
);
"""

TRACKS = {
    "texas":   "Texas data center buildout: ERCOT, PUCT, permits, generation",
    "silicon": "AI chip competition: CUDA moat, alternative silicon, pricing power",
    "desk":    "Event desk: event odds, conditional reactions, setups",
    "other":   "Unclassified",
}

CATEGORIES = {
    "approval":   ("texas",   "Which projects clear regulatory gates"),
    "bottleneck": ("texas",   "Which suppliers benefit from the power constraint"),
    "policy":     ("texas",   "Which entities benefit from rule changes"),
    "moat":       ("silicon", "CUDA lock erosion: framework abstraction, benchmarks"),
    "adoption":   ("silicon", "Who actually deploys non-Nvidia silicon at scale"),
    "pricing":    ("silicon", "Nvidia value capture: rev/GW, ASPs, resale, collateral"),
    "event":      ("desk",    "Will a named event happen by a date"),
    "reaction":   ("desk",    "Conditional market reaction with a measurable threshold"),
    "setup":      ("desk",    "A setup's measurable outcome over a stated window"),
    "other":      ("other",   "Anything else"),
}


BASIS = {
    "unread_source": "A primary source few people read: a docket, a filing, a permit",
    "engineering":   "Physical or technical judgment about whether something can work",
    "headline":      "News reporting that everyone else can also read",
    "scheduled":     "A published date or deadline",
    "market":        "A market price, such as a prediction market or options pricing",
    "other":         "None of the above",
}


def norm_basis(value: str | None) -> str:
    v = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return v if v in BASIS else "other"


def track_of(category: str) -> str:
    return CATEGORIES.get(category, ("other", ""))[0]


def describe(category: str) -> str:
    return CATEGORIES.get(category, ("other", "Anything else"))[1]


SCHEMA_AUDIT = """
CREATE TABLE IF NOT EXISTS snapshots (
    hash        TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    size        INTEGER NOT NULL,
    body        BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_inputs (
    claim_id      TEXT NOT NULL,
    origin        TEXT NOT NULL,
    snapshot_hash TEXT,
    model         TEXT,
    provider      TEXT,
    prompt_hash   TEXT,
    sources       TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inputs_claim ON claim_inputs(claim_id);
"""

SCHEMA_LOCKS = """
CREATE TRIGGER IF NOT EXISTS lock_claim_fields
BEFORE UPDATE OF claim, category, confidence, resolve_by, created_at, subject,
                 mechanism, evidence, basis ON hypotheses
BEGIN SELECT RAISE(ABORT, 'calls are append-only: log a new claim instead'); END;

CREATE TRIGGER IF NOT EXISTS lock_closed_claims
BEFORE UPDATE OF status, outcome ON hypotheses
WHEN OLD.status != 'open'
BEGIN SELECT RAISE(ABORT, 'this call is already graded or void'); END;

CREATE TRIGGER IF NOT EXISTS lock_no_delete_claims
BEFORE DELETE ON hypotheses
BEGIN SELECT RAISE(ABORT, 'calls are never deleted'); END;

CREATE TRIGGER IF NOT EXISTS lock_inputs_update
BEFORE UPDATE ON claim_inputs
BEGIN SELECT RAISE(ABORT, 'input records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS lock_inputs_delete
BEFORE DELETE ON claim_inputs
BEGIN SELECT RAISE(ABORT, 'input records are append-only'); END;

CREATE TRIGGER IF NOT EXISTS lock_snapshots_update
BEFORE UPDATE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are append-only'); END;
CREATE TRIGGER IF NOT EXISTS lock_snapshots_delete
BEFORE DELETE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are append-only'); END;
"""


def conn() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(hypotheses)")}
    if "basis" not in cols:
        c.execute("ALTER TABLE hypotheses ADD COLUMN basis TEXT DEFAULT 'other'")
    c.executescript(SCHEMA_AUDIT)
    c.executescript(SCHEMA_LOCKS)
    c.row_factory = sqlite3.Row
    return c


WEASEL = [
    "could", "might", "may ", "possibly", "potentially", "likely to see",
    "some", "various", "significant", "substantial", "material impact",
    "well positioned", "poised", "benefit from", "headwind", "tailwind",
]


def validate_claim(claim: str) -> list[str]:
    problems = []
    low = claim.lower()

    for w in WEASEL:
        if w in low:
            problems.append(f"vague term '{w.strip()}' — rewrite so it can be marked false")

    if len(claim.split()) < 6:
        problems.append("too short to be specific")

    has_anchor = (
        any(ch.isdigit() for ch in claim)
        or any(w[0].isupper() for w in claim.split()[1:])
    )
    if not has_anchor:
        problems.append("no number, name or date — nothing concrete to check against")

    return problems


def add(claim: str, category: str, confidence: float, resolve_by: str,
        subject: str = "", mechanism: str = "", evidence: str = "",
        force: bool = False, basis: str = "other") -> str | None:
    problems = validate_claim(claim)
    if problems and not force:
        print("Claim rejected as not falsifiable:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\nGood:  'ERCOT files its verification report with the PUCT on or "
              "before 2026-12-10'", file=sys.stderr)
        print("Bad:   'The audit could significantly impact data center "
              "developers'", file=sys.stderr)
        return None

    if not 0.0 <= confidence <= 1.0:
        print("confidence must be between 0.0 and 1.0", file=sys.stderr)
        return None

    try:
        dt.date.fromisoformat(resolve_by)
    except ValueError:
        print("resolve_by must be ISO format YYYY-MM-DD", file=sys.stderr)
        return None

    if category not in CATEGORIES:
        print(f"category must be one of: {', '.join(CATEGORIES)}", file=sys.stderr)
        return None

    hid = uuid.uuid4().hex[:8]
    c = conn()
    c.execute(
        """INSERT INTO hypotheses
           (id, created_at, claim, subject, category, mechanism,
            confidence, resolve_by, evidence, basis)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (hid, dt.datetime.now().isoformat(timespec="seconds"), claim, subject,
         category, mechanism, confidence, resolve_by, evidence, norm_basis(basis)),
    )
    c.commit()
    c.close()

    try:
        import panel
        panel.add_free(hid, category, confidence)
    except Exception as exc:
        print(f"warning: panel members not logged for {hid}: {exc}", file=sys.stderr)

    return hid


def resolve(hid: str, outcome: bool, note: str = "") -> bool:
    c = conn()
    row = c.execute("SELECT * FROM hypotheses WHERE id=?", (hid,)).fetchone()
    if not row:
        print(f"No hypothesis {hid}", file=sys.stderr)
        c.close()
        return False
    if row["status"] != "open":
        print(f"{hid} already resolved as {row['outcome']}", file=sys.stderr)
        c.close()
        return False

    c.execute(
        """UPDATE hypotheses
           SET status='resolved', outcome=?, resolved_at=?, resolution_note=?
           WHERE id=?""",
        (int(outcome), dt.datetime.now().isoformat(timespec="seconds"), note, hid),
    )
    c.commit()
    c.close()
    return True


def void(hid: str, note: str = "") -> bool:
    c = conn()
    row = c.execute("SELECT * FROM hypotheses WHERE id=?", (hid,)).fetchone()
    if not row:
        print(f"No hypothesis {hid}", file=sys.stderr)
        c.close()
        return False
    if row["status"] != "open":
        print(f"{hid} is already {row['status']}", file=sys.stderr)
        c.close()
        return False

    c.execute(
        """UPDATE hypotheses
           SET status='void', resolved_at=?, resolution_note=?
           WHERE id=?""",
        (dt.datetime.now().isoformat(timespec="seconds"), note, hid),
    )
    c.commit()
    c.close()
    return True


def brier(rows) -> float:
    if not rows:
        return float("nan")
    return sum((r["confidence"] - r["outcome"]) ** 2 for r in rows) / len(rows)


def score_report() -> int:
    c = conn()
    resolved = c.execute(
        "SELECT * FROM hypotheses WHERE status='resolved'"
    ).fetchall()
    open_rows = c.execute(
        "SELECT * FROM hypotheses WHERE status='open'"
    ).fetchall()
    void_n = c.execute(
        "SELECT COUNT(*) FROM hypotheses WHERE status='void'"
    ).fetchone()[0]
    c.close()

    print("CALIBRATION REPORT\n")
    print(f"  resolved: {len(resolved)}    open: {len(open_rows)}    "
          f"void: {void_n}\n")
    if void_n and resolved and void_n > len(resolved):
        print("  More claims voided than resolved. Void is for conditions that")
        print("  never happened, not for misses. Check the void notes.\n")

    if len(resolved) < 10:
        print(f"  Only {len(resolved)} resolved claims. Scoring needs at least")
        print("  10 to mean anything, and 30+ before you should believe it.")
        print("  Keep running. Do not act on a 3-claim sample.")
        return 0

    overall = brier(resolved)
    hit_rate = sum(r["outcome"] for r in resolved) / len(resolved)
    mean_conf = sum(r["confidence"] for r in resolved) / len(resolved)

    print(f"  Brier score:      {overall:.4f}")
    print(f"  Hit rate:         {hit_rate:.1%}")
    print(f"  Mean confidence:  {mean_conf:.1%}")
    print()

    if overall > 0.25:
        print("  WORSE THAN A COIN FLIP (0.25 baseline).")
        print("  The logic is not producing signal. That is a real result and")
        print("  it is the cheapest one you will ever get. Stop or redesign.")
    elif overall > 0.20:
        print("  Marginally better than chance. Within noise at this sample")
        print("  size. Not evidence of edge.")
    else:
        print("  Better than chance. Check per-category breakdown before")
        print("  concluding anything — one category may carry the whole result.")
    print()

    gap = mean_conf - hit_rate
    if abs(gap) > 0.10:
        direction = "OVERCONFIDENT" if gap > 0 else "UNDERCONFIDENT"
        print(f"  {direction} by {abs(gap):.1%}. Stated confidence does not")
        print(f"  match observed hit rate. Adjust the analyst prompt.")
        print()

    print("  BY TRACK")
    for track, tdesc in TRACKS.items():
        trows = [r for r in resolved if track_of(r["category"]) == track]
        if not trows:
            continue
        tb = brier(trows)
        thr = sum(r["outcome"] for r in trows) / len(trows)
        verdict = "worse than chance" if tb > 0.25 else (
            "within noise" if tb > 0.20 else "better than chance")
        print(f"    {track.upper():<9} n={len(trows):<4} Brier={tb:.4f}  "
              f"hits={thr:.0%}   {verdict}")
        if len(trows) < 15:
            print(f"              (n<15 — not enough to mean much yet)")

        for cat in [c for c, (t, _) in CATEGORIES.items() if t == track]:
            rows = [r for r in trows if r["category"] == cat]
            if not rows:
                print(f"       {cat:<11} (none resolved)")
                continue
            b = brier(rows)
            hr = sum(r["outcome"] for r in rows) / len(rows)
            flag = "  <-- worse than chance" if b > 0.25 else ""
            print(f"       {cat:<11} n={len(rows):<4} Brier={b:.4f}  hits={hr:.0%}{flag}")
        print()

    print("  CALIBRATION BUCKETS (stated confidence vs actual)")
    for lo in [0.0, 0.2, 0.4, 0.6, 0.8]:
        hi = lo + 0.2
        rows = [r for r in resolved if lo <= r["confidence"] < hi or
                (hi == 1.0 and r["confidence"] == 1.0)]
        if not rows:
            continue
        actual = sum(r["outcome"] for r in rows) / len(rows)
        print(f"    said {lo:.0%}-{hi:.0%}:  actual {actual:>5.0%}   (n={len(rows)})")

    print("\n  Perfect calibration means stated and actual match in every bucket.")

    print("\n  BY WHAT THE CALL RESTED ON")
    for b in BASIS:
        rows = [r for r in resolved if (r["basis"] or "other") == b]
        if not rows:
            continue
        bb = brier(rows)
        flag = "  <-- worse than chance" if bb > 0.25 else ""
        print(f"    {b:<14} n={len(rows):<4} Brier={bb:.4f}{flag}")

    try:
        import panel
        print()
        print("\n".join(panel.report_lines()))
    except Exception as exc:
        print(f"\n  (panel report unavailable: {exc})")
    return 0


def list_open(due_only: bool) -> int:
    c = conn()
    if due_only:
        rows = c.execute(
            "SELECT * FROM hypotheses WHERE status='open' AND resolve_by<=? "
            "ORDER BY resolve_by", (dt.date.today().isoformat(),)
        ).fetchall()
        header = "CLAIMS DUE FOR RESOLUTION"
    else:
        rows = c.execute(
            "SELECT * FROM hypotheses WHERE status='open' ORDER BY resolve_by"
        ).fetchall()
        header = "OPEN CLAIMS"
    c.close()

    print(f"{header}\n")
    if not rows:
        print("  (none)")
        return 0

    today = dt.date.today()
    for r in rows:
        due = dt.date.fromisoformat(r["resolve_by"])
        days = (due - today).days
        when = f"{days}d" if days >= 0 else f"{-days}d OVERDUE"
        print(f"  [{r['id']}] {track_of(r['category'])}/{r['category']:<11} "
              f"conf {r['confidence']:.0%}  due {r['resolve_by']} ({when})")
        print(f"    {r['claim']}")
        if r["subject"]:
            print(f"    subject: {r['subject']}")
        if r["mechanism"]:
            print(f"    why: {r['mechanism']}")
        print()

    if due_only and rows:
        print(f"  Resolve with: python ledger.py --resolve <id> true|false")
    return 0


def export() -> int:
    c = conn()
    rows = [dict(r) for r in c.execute("SELECT * FROM hypotheses ORDER BY created_at").fetchall()]
    c.close()
    print(json.dumps(rows, indent=2))
    return 0


def interactive_add() -> int:
    print("Add a hypothesis. It must be checkable as true or false.\n")
    print("Categories, by track:")
    for track, tdesc in TRACKS.items():
        cats = [c for c, (t, _) in CATEGORIES.items() if t == track]
        if not cats:
            continue
        print(f"  [{track}] {tdesc}")
        for c in cats:
            print(f"    {c:<12} {describe(c)}")
    print()

    claim = input("Claim: ").strip()
    problems = validate_claim(claim)
    if problems:
        print("\nThis is not falsifiable yet:")
        for p in problems:
            print(f"  - {p}")
        if input("\nAdd anyway? (y/N): ").strip().lower() != "y":
            return 1

    category = input(f"Category [{'/'.join(CATEGORIES)}]: ").strip() or "other"
    subject = input("Subject (ticker/company/project, optional): ").strip()
    mechanism = input("Mechanism (why would this be true?): ").strip()
    try:
        confidence = float(input("Confidence 0.0-1.0: ").strip())
    except ValueError:
        print("Invalid confidence.", file=sys.stderr)
        return 1
    resolve_by = input("Resolve by (YYYY-MM-DD): ").strip()
    evidence = input("Evidence (URLs, comma separated): ").strip()

    hid = add(claim, category, confidence, resolve_by, subject, mechanism,
              evidence, force=True)
    if hid:
        print(f"\nRecorded as {hid}, resolves {resolve_by}.")
        return 0
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--add", action="store_true", help="add interactively")
    p.add_argument("--open", action="store_true", help="list unresolved claims")
    p.add_argument("--due", action="store_true", help="list claims past resolution date")
    p.add_argument("--resolve", nargs=2, metavar=("ID", "TRUE_FALSE_OR_VOID"),
                   help="grade a claim: true, false, or void (condition never occurred)")
    p.add_argument("--new", metavar="CLAIM",
                   help="add a claim non-interactively (needs --category --confidence --by)")
    p.add_argument("--category", default="other")
    p.add_argument("--confidence", type=float, default=None)
    p.add_argument("--by", default="", help="resolution date YYYY-MM-DD")
    p.add_argument("--why", default="", help="mechanism / reasoning")
    p.add_argument("--subject", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--basis", default="other", choices=list(BASIS),
                   help="what the call rested on")
    p.add_argument("--note", default="", help="note to attach when resolving")
    p.add_argument("--score", action="store_true", help="calibration report")
    p.add_argument("--export", action="store_true", help="dump all as JSON")
    args = p.parse_args()

    if args.add:
        return interactive_add()
    if args.new:
        if args.confidence is None or not args.by:
            print("--new needs --confidence and --by", file=sys.stderr)
            return 1
        hid = add(args.new, args.category, args.confidence, args.by,
                  subject=args.subject, mechanism=args.why,
                  evidence=args.evidence, basis=args.basis)
        if hid:
            import snapshots
            snapshots.attach(hid, "chat", inputs=f"WHY: {args.why}\nEVIDENCE: {args.evidence}")
            print(f"Recorded {hid} [{track_of(args.category)}/{args.category}] "
                  f"conf {args.confidence:.0%}, resolves {args.by}")
            return 0
        return 1
    if args.resolve:
        hid, val = args.resolve
        v = val.strip().lower()
        if v == "void":
            ok = void(hid, args.note)
            if ok:
                print(f"{hid} voided (excluded from scoring).")
            return 0 if ok else 1
        if v not in ("true", "t", "yes", "y", "1", "false", "f", "no", "n", "0"):
            print("outcome must be true, false, or void", file=sys.stderr)
            return 1
        outcome = v in ("true", "t", "yes", "y", "1")
        ok = resolve(hid, outcome, args.note)
        if ok:
            print(f"{hid} resolved as {outcome}.")
        return 0 if ok else 1
    if args.score:
        return score_report()
    if args.export:
        return export()
    if args.due:
        return list_open(due_only=True)

    return list_open(due_only=False)


if __name__ == "__main__":
    sys.exit(main())
