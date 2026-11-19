#!/usr/bin/env python3
"""Answer the pre-registered audit questions on an exported bundle. Standard library only.

    python analyze_audit.py audit-YYYYMMDD-HHMM.zip
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

SHOWN = "_blend"
BASES = ["unread_source", "engineering", "headline", "scheduled", "market", "other"]


def brier(pairs):
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else None


def vs_coin(pairs):
    d = [(p - y) ** 2 - (0.5 - y) ** 2 for p, y in pairs]
    if len(d) < 2:
        return None, None
    m = sum(d) / len(d)
    v = sum((x - m) ** 2 for x in d) / (len(d) - 1)
    return m, math.sqrt(v / len(d))


def verdict(pairs):
    n = len(pairs)
    if n < 15:
        return f"n={n:<4} too few to say"
    b = brier(pairs)
    m, se = vs_coin(pairs)
    if m is None or abs(m) <= 2 * se:
        call = "no clear difference from a coin flip"
    elif m < 0:
        call = f"better than a coin flip by {-m:.3f} (+/- {se:.3f})"
    else:
        call = f"WORSE than a coin flip by {m:.3f} (+/- {se:.3f})"
    tag = "" if n >= 30 else "  [hint only, n<30]"
    return f"n={n:<4} Brier {b:.3f}  {call}{tag}"


def holdout_line(train, test):
    if len(test) < 5 or len(train) < 15:
        return "      hold-out: too few calls in the held-out month to check"
    m_tr, _ = vs_coin(train)
    m_te, _ = vs_coin(test)
    if m_tr is None or m_te is None:
        return "      hold-out: not checkable"
    same = (m_tr < 0) == (m_te < 0)
    return (f"      hold-out ({len(test)} calls): {'same direction' if same else 'DID NOT HOLD'}"
            f" (train {m_tr:+.3f}, held-out {m_te:+.3f})")


def section(title, groups, train_rows, test_rows, key):
    out = [title]
    any_ = False
    for g in groups:
        tr = [(r["p"], r["y"]) for r in train_rows if key(r) == g]
        te = [(r["p"], r["y"]) for r in test_rows if key(r) == g]
        if not tr and not te:
            continue
        any_ = True
        out.append(f"  {g:<18} {verdict(tr)}")
        if len(tr) >= 15:
            out.append(holdout_line(tr, te))
    if not any_:
        out.append("  (no graded calls in any group yet)")
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    bundle = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if zipfile.is_zipfile(bundle):
            with zipfile.ZipFile(bundle) as z:
                for m in z.infolist():
                    if "/" in m.filename or m.filename.startswith(".") or m.is_dir():
                        raise SystemExit(f"unexpected entry in bundle: {m.filename}")
                z.extractall(tmp)
        else:
            with tarfile.open(bundle) as tar:
                for m in tar.getmembers():
                    if "/" in m.name or m.name.startswith(".") or not m.isfile():
                        raise SystemExit(f"unexpected entry in bundle: {m.name}")
                tar.extractall(tmp)
        manifest = json.loads((tmp / "manifest.json").read_text())
        c = sqlite3.connect(tmp / "ledger.db")
        c.row_factory = sqlite3.Row

        holdout = manifest["holdout_from"]
        claims = [dict(r) for r in c.execute(
            "SELECT * FROM hypotheses WHERE status='resolved'")]
        inputs = {}
        for r in c.execute("SELECT claim_id, origin, sources FROM claim_inputs"):
            inputs.setdefault(r["claim_id"], []).append(dict(r))
        fc = {}
        for r in c.execute("SELECT claim_id, member, prob FROM forecasts"):
            fc.setdefault(r["claim_id"], {})[r["member"]] = r["prob"]

    rows = []
    for cl in claims:
        try:
            made = dt.datetime.fromisoformat(cl["created_at"]).date()
            due = dt.date.fromisoformat(cl["resolve_by"])
            lead = (due - made).days
        except (TypeError, ValueError):
            lead = None
        srcs = ",".join(i["sources"] for i in inputs.get(cl["id"], [])
                        if i["origin"] == "loop" and i["sources"])
        rows.append({"p": cl["confidence"], "y": float(cl["outcome"]),
                     "basis": cl.get("basis") or "other", "sources": srcs,
                     "lead": lead, "graded": (cl["resolved_at"] or "")[:10],
                     "id": cl["id"]})

    train = [r for r in rows if r["graded"] < holdout]
    test = [r for r in rows if r["graded"] >= holdout]

    L = [f"AUDIT REPORT for {bundle.name}",
         f"Exported {manifest['created_at']}. Integrity check: {manifest['integrity_check']}.",
         f"{len(rows)} graded calls: {len(train)} analysed, {len(test)} held out "
         f"(graded on or after {holdout}).",
         "Brier: 0 is perfect, 0.25 is a coin flip. Lower is better.",
         "Only the five pre-registered questions are answered here.", ""]

    if len(train) < 15:
        L.append("Too few graded calls before the hold-out month to answer anything yet.")
        L.append("Keep grading; re-run after the next export.")
        print("\n".join(L))
        return 0

    L += section("Q1. Which kind of evidence has been worth trusting?",
                 BASES, train, test, lambda r: r["basis"])
    L.append("")

    src_names = sorted({s for r in rows for s in r["sources"].split(",") if s})
    L += section("Q2. Which sources produce calls that hold up? (research-loop calls only)",
                 src_names, train, test,
                 lambda r: next((s for s in r["sources"].split(",") if s), None))
    if not src_names:
        L.append("  (no research-loop calls graded yet)")
    L.append("")

    L.append("Q3. Are the odds honest?")
    for label, getp in (("stated odds", lambda r: r["p"]),
                        ("panel blend", lambda r: fc.get(r["id"], {}).get(SHOWN))):
        pairs = [(getp(r), r["y"]) for r in train if getp(r) is not None]
        if len(pairs) < 15:
            L.append(f"  {label:<12} too few")
            continue
        mean_p = sum(p for p, _ in pairs) / len(pairs)
        hit = sum(y for _, y in pairs) / len(pairs)
        gap = mean_p - hit
        lean = ("overconfident" if gap > 0.05 else "too cautious" if gap < -0.05
                else "about right")
        L.append(f"  {label:<12} said {mean_p:.0%} on average, {hit:.0%} came true: {lean}")
        for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
            b = [(p, y) for p, y in pairs if lo <= p < lo + 0.2 or (lo == 0.8 and p >= 1.0)]
            if len(b) >= 5:
                L.append(f"      said {lo:.0%}-{lo + .2:.0%}: {sum(y for _, y in b) / len(b):.0%} came true (n={len(b)})")
    L.append("")

    L.append("Q4. Which forecaster leads, and by more than luck?")
    members = sorted({m for d in fc.values() for m in d if m != SHOWN})
    lines = []
    for m in members:
        tr = [(fc[r["id"]][m], r["y"]) for r in train if m in fc.get(r["id"], {})]
        te = [(fc[r["id"]][m], r["y"]) for r in test if m in fc.get(r["id"], {})]
        if not tr:
            continue
        lines.append((brier(tr) if len(tr) >= 15 else 9, m, tr, te))
    for _, m, tr, te in sorted(lines):
        L.append(f"  {m:<18} {verdict(tr)}")
        if len(tr) >= 15 and m != "coin":
            L.append(holdout_line(tr, te))
    L.append("")

    L += section("Q5. Does accuracy change with how far ahead the call was made?",
                 ["under 7 days", "7 to 30 days", "over 30 days"], train, test,
                 lambda r: None if r["lead"] is None else
                 "under 7 days" if r["lead"] < 7 else
                 "7 to 30 days" if r["lead"] <= 30 else "over 30 days")
    L.append("")
    L.append("Reminder: anything that is not one of these five answers is a hint.")
    L.append("Turn it into a new panel member or claim and let it prove itself forward.")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
