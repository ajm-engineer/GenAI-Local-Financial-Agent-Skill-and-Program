#!/usr/bin/env python3
"""Continuous research loop: extracts falsifiable claims from new sources and logs them.

    python research_loop.py --once
    python research_loop.py --daemon
    python research_loop.py --report
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
STATE_DB = DATA / "research_state.db"

sys.path.insert(0, str(HERE))
import ledger
import llm
import panel
import snapshots

log = logging.getLogger("research")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_state (
    source_id   TEXT PRIMARY KEY,
    last_hash   TEXT,
    last_seen   TEXT,
    last_change TEXT,
    poll_count  INTEGER DEFAULT 0,
    fail_count  INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cycles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at      TEXT NOT NULL,
    changes     INTEGER DEFAULT 0,
    analysed    INTEGER DEFAULT 0,
    hypotheses  INTEGER DEFAULT 0,
    notes       TEXT
);
"""

SOURCES = [
    {"id": "puct_interchange", "track": "texas", "interval_hours": 6,
     "url": "https://interchange.puc.texas.gov",
     "desc": "PUCT filings. Project 58481 is the large-load rulemaking docket."},
    {"id": "ercot_notices", "track": "texas", "interval_hours": 6,
     "url": "https://www.ercot.com",
     "desc": "ERCOT market notices, board and TAC agendas."},
    {"id": "txef_program", "track": "texas", "interval_hours": 24,
     "url": "https://www.puc.texas.gov/industry/electric/business/texas-energy-fund/",
     "desc": "Texas Energy Fund awards AND withdrawals. Withdrawals matter more."},
    {"id": "tceq_permits", "track": "texas", "interval_hours": 24,
     "url": "https://www.tceq.texas.gov",
     "desc": "Environmental permits. Became a gate 2026-09-21."},
    {"id": "sec_edgar", "track": "both", "interval_hours": 4,
     "url": "https://data.sec.gov",
     "desc": "8-K and Form 4 for tracked tickers."},

    {"id": "pytorch_releases", "track": "silicon", "interval_hours": 24,
     "url": "https://github.com/pytorch/pytorch/releases",
     "desc": "PyTorch releases. Backend support changes land here first."},
    {"id": "pytorch_xla", "track": "silicon", "interval_hours": 24,
     "url": "https://github.com/pytorch/xla/releases",
     "desc": "PyTorch/XLA — the TPU backend. TorchTPU work surfaces here."},
    {"id": "mlperf_results", "track": "silicon", "interval_hours": 72,
     "url": "https://mlcommons.org/benchmarks/",
     "desc": "MLPerf. The closest thing to neutral cross-vendor benchmarks."},
    {"id": "amd_ir", "track": "silicon", "interval_hours": 12,
     "url": "https://ir.amd.com",
     "desc": "AMD investor relations. Instinct accelerator revenue, MI450 "
             "milestones, supply agreements."},
    {"id": "nvidia_ir", "track": "silicon", "interval_hours": 12,
     "url": "https://investor.nvidia.com",
     "desc": "Nvidia IR. Revenue per gigawatt and margin disclosures."},
]

ANALYST_SYSTEM = """\
You are a research analyst producing FALSIFIABLE hypotheses about the Texas \
data center buildout and its supply chain.

TWO TRACKS. Pick the category that fits; never mix tracks in one claim.

TEXAS track (regulation, resolves in weeks to months on published dates):
  approval   - which specific projects clear which specific regulatory gates
  bottleneck - which suppliers benefit from the power/permit constraint
  policy     - which entities benefit from specific rule changes

SILICON track (chip competition, resolves over quarters via benchmarks and
earnings disclosures):
  moat       - CUDA lock erosion: framework abstraction, published benchmarks
  adoption   - who actually deploys non-Nvidia silicon at scale
  pricing    - Nvidia value capture: revenue per gigawatt, ASPs, GPU resale
               values, lending LTVs

Note on PyTorch and CUDA: PyTorch sits ABOVE CUDA in the stack. Swapping the
layers beneath PyTorch is the entire strategy. A claim that inverts this is
wrong on the mechanism and will grade badly.

OUTPUT FORMAT: a JSON array. Nothing else. No preamble, no markdown fences.

Each object:
{
  "claim": "a statement checkable as TRUE or FALSE on a specific date",
  "category": "approval" | "bottleneck" | "policy" | "moat" | "adoption" | "pricing",
  "subject": "ticker, company or project name",
  "mechanism": "the causal chain, one or two sentences",
  "confidence": 0.0 to 1.0,
  "resolve_by": "YYYY-MM-DD",
  "evidence": "source URLs or document references",
  "basis": "unread_source | engineering | headline | scheduled | market | other"
}

BASIS is what the claim mainly rests on. Most claims from a PUCT, ERCOT or
SEC page are "unread_source"; claims about a published deadline are
"scheduled". Be honest: each basis is scored separately.

RULES FOR CLAIMS:

1. A claim must be markable FALSE. If no observable outcome could falsify it, \
do not write it.
   GOOD: "ERCOT files its verification report with the PUCT on or before \
2026-12-10"
   GOOD: "Fewer than 5 of the 17 paused projects receive Approval to Energize \
by 2027-03-31"
   BAD:  "The audit could significantly impact developers"
   BAD:  "GE Vernova is well positioned to benefit from turbine demand"

2. Banned words, because they make a claim ungradeable: could, might, may, \
possibly, potentially, significant, substantial, well positioned, poised, \
benefit from, headwind, tailwind.

3. Every claim needs a number, a named entity, or a date. Preferably all three.

4. DO NOT make claims about stock prices or returns. Not "NVDA rises 5%", not \
"outperforms the sector". Price movement over short horizons is not \
predictable from regulatory filings, and a claim you cannot support \
contaminates the calibration score for the claims you can.
   Make claims about OBSERVABLE WORLD EVENTS: filings, approvals, awards, \
withdrawals, capacity figures, announced contracts, published deadlines.

5. Confidence must be honest. If you state 0.9 you should be right nine times \
in ten. Overconfidence shows up in the calibration report and invalidates the \
whole exercise.

6. If the input contains nothing that supports a falsifiable claim, return an \
empty array. A quiet day is a valid result. Manufacturing claims to fill \
output is the failure mode this system exists to avoid.

Typical output: 0 to 3 claims. More than 5 means you are padding.
"""


def db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(STATE_DB)
    c.executescript(STATE_SCHEMA)
    c.row_factory = sqlite3.Row
    return c


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def due_sources() -> list[dict]:
    c = db()
    now = dt.datetime.now()
    out = []
    for s in SOURCES:
        row = c.execute("SELECT * FROM source_state WHERE source_id=?",
                        (s["id"],)).fetchone()
        if row is None or row["last_seen"] is None:
            out.append(s)
            continue
        last = dt.datetime.fromisoformat(row["last_seen"])
        if (now - last).total_seconds() >= s["interval_hours"] * 3600:
            out.append(s)
    c.close()
    return out


def poll(source: dict) -> tuple[bool, str | None]:
    c = db()
    try:
        resp = requests.get(source["url"], timeout=30,
                            headers={"User-Agent": os.environ.get(
                                "SEC_USER_AGENT", "market-digest research loop")})
        resp.raise_for_status()
        text = resp.text
    except Exception as exc:
        log.warning("poll failed for %s: %s", source["id"], exc)
        c.execute(
            """INSERT INTO source_state (source_id, last_seen, fail_count)
               VALUES (?,?,1)
               ON CONFLICT(source_id) DO UPDATE SET
                 last_seen=excluded.last_seen,
                 fail_count=fail_count+1""",
            (source["id"], dt.datetime.now().isoformat(timespec="seconds")))
        c.commit()
        c.close()
        return False, None

    h = content_hash(text)
    row = c.execute("SELECT last_hash FROM source_state WHERE source_id=?",
                    (source["id"],)).fetchone()
    changed = row is None or row["last_hash"] != h
    now_iso = dt.datetime.now().isoformat(timespec="seconds")

    c.execute(
        """INSERT INTO source_state
             (source_id, last_hash, last_seen, last_change, poll_count)
           VALUES (?,?,?,?,1)
           ON CONFLICT(source_id) DO UPDATE SET
             last_hash=excluded.last_hash,
             last_seen=excluded.last_seen,
             last_change=CASE WHEN source_state.last_hash != excluded.last_hash
                              THEN excluded.last_seen
                              ELSE source_state.last_change END,
             poll_count=source_state.poll_count+1""",
        (source["id"], h, now_iso, now_iso))
    c.commit()
    c.close()
    return changed, text


def analyse(changes: list[dict], config: dict) -> list[dict]:
    tracks = {ch.get("track", "texas") for ch in changes}
    names = []
    if "texas" in tracks or "both" in tracks:
        names += ["texas-datacenter.md", "texas-generation.md",
                  "bottleneck-supply-chain.md"]
    if "silicon" in tracks or "both" in tracks:
        names += ["silicon-competition.md"]

    refs = []
    for name in names:
        pth = HERE.parent / "references" / name
        if pth.exists():
            refs.append(f"=== {name} ===\n{pth.read_text()}")

    provider = config.get("digest", {}).get("provider", "anthropic").lower()

    excerpt_cap = 1500 if provider == "ollama" else 4000
    if provider == "ollama":
        refs = [r[:6000] for r in refs]

    payload = "\n\n".join(
        f"SOURCE: {ch['id']} ({ch['desc']})\nURL: {ch['url']}\n"
        f"CHANGED AT: {ch['at']}\nEXCERPT:\n{ch['excerpt'][:excerpt_cap]}"
        for ch in changes)

    user_text = ("DOMAIN REFERENCE:\n" + "\n\n".join(refs) +
                 "\n\n=== CHANGED SOURCES ===\n" + payload +
                 "\n\nProduce falsifiable hypotheses as a JSON array. "
                 "Empty array if nothing supports one.")
    LAST_INPUT["text"] = user_text
    LAST_INPUT["sources"] = ",".join(ch["id"] for ch in changes)

    try:
        text = llm.complete(
            system=ANALYST_SYSTEM,
            user=user_text,
            config=config,
            want_json=True,
            max_tokens=3000,
        )
        return llm.parse_json_array(text)
    except llm.LLMError as exc:
        log.error("analysis failed: %s", exc)
        return []
    except Exception as exc:
        log.error("could not parse analyst output: %s", exc)
        return []


ANTHROPIC_SYSTEM_CACHE = None


LAST_INPUT: dict = {"text": "", "sources": ""}


def record(hypotheses: list[dict], config: dict) -> int:
    kept = 0
    new_claims: list[dict] = []
    for h in hypotheses:
        claim = h.get("claim", "")
        problems = ledger.validate_claim(claim)
        if problems:
            log.warning("rejected unfalsifiable claim: %s", claim[:80])
            for p in problems:
                log.warning("    %s", p)
            continue

        category = h.get("category", "other")
        if ledger.track_of(category) == "desk":
            log.warning("rejected desk-track claim from the research loop: %s",
                        claim[:70])
            continue
        try:
            model_conf = float(h["confidence"]) if "confidence" in h else None
        except (TypeError, ValueError):
            model_conf = None

        confidence, conf_source = llm.assign_confidence(
            category, model_conf, config, ledger.DB)

        hid = ledger.add(
            claim=claim,
            category=category,
            confidence=confidence,
            resolve_by=h.get("resolve_by", ""),
            subject=h.get("subject", ""),
            mechanism=h.get("mechanism", ""),
            evidence=h.get("evidence", ""),
            basis=ledger.norm_basis(h.get("basis")),
        )
        if hid:
            model, prov = snapshots.model_name(llm.settings_for(config))
            snapshots.attach(hid, "loop", inputs=LAST_INPUT["text"], model=model,
                             provider=prov, prompt=ANALYST_SYSTEM,
                             sources=LAST_INPUT["sources"])
            kept += 1
            new_claims.append({"id": hid, "claim": claim,
                               "why": h.get("mechanism", "")})
            log.info("recorded %s (conf %.2f via %s): %s",
                     hid, confidence, conf_source, claim[:60])
            if model_conf is not None and conf_source != "model":
                panel.record(hid, "analyst_raw",
                             model_conf / 100.0 if model_conf > 1.0 else model_conf)
                panel.stamp_shown(hid)

    if new_claims and (config.get("panel") or {}).get("in_loop", True):
        context = "\n".join(f"- {c['claim']} (reasoning given: {c['why']})"
                            for c in new_claims)
        for err in panel.llm_forecasts(new_claims, context, config):
            log.warning(err)
    return kept


def load_config() -> dict:
    return yaml.safe_load((HERE.parent / "config.yaml").read_text())


def cycle(dry_run: bool) -> dict:
    config = load_config()
    provider = config.get("digest", {}).get("provider", "anthropic")
    log.info("provider: %s", provider)

    due = due_sources()
    log.info("%d source(s) due for polling", len(due))

    changes = []
    for s in due:
        changed, text = poll(s)
        if changed and text:
            log.info("CHANGED: %s", s["id"])
            changes.append({**s, "at": dt.datetime.now().isoformat(timespec="seconds"),
                            "excerpt": text})
        elif text:
            log.debug("unchanged: %s", s["id"])

    if not changes:
        log.info("no changes - skipping analysis (this is normal and cheap)")
        return {"changes": 0, "analysed": 0, "hypotheses": 0}

    hypotheses = analyse(changes, config)
    log.info("analyst produced %d candidate hypotheses", len(hypotheses))

    if dry_run:
        print(json.dumps(hypotheses, indent=2))
        return {"changes": len(changes), "analysed": len(hypotheses), "hypotheses": 0}

    kept = record(hypotheses, config)

    c = db()
    c.execute("INSERT INTO cycles (ran_at, changes, analysed, hypotheses) "
              "VALUES (?,?,?,?)",
              (dt.datetime.now().isoformat(timespec="seconds"),
               len(changes), len(hypotheses), kept))
    c.commit()
    c.close()

    return {"changes": len(changes), "analysed": len(hypotheses), "hypotheses": kept}


def report(hours: int) -> int:
    cutoff = (dt.datetime.now() - dt.timedelta(hours=hours)).isoformat()

    c = db()
    cycles = c.execute("SELECT * FROM cycles WHERE ran_at>=? ORDER BY ran_at",
                       (cutoff,)).fetchall()
    states = c.execute("SELECT * FROM source_state").fetchall()
    c.close()

    lc = ledger.conn()
    new = lc.execute("SELECT * FROM hypotheses WHERE created_at>=? "
                     "ORDER BY confidence DESC", (cutoff,)).fetchall()
    due = lc.execute("SELECT * FROM hypotheses WHERE status='open' AND resolve_by<=?",
                     (dt.date.today().isoformat(),)).fetchall()
    lc.close()

    print(f"RESEARCH REPORT - last {hours}h\n")
    print(f"  cycles run:        {len(cycles)}")
    print(f"  source changes:    {sum(x['changes'] for x in cycles)}")
    print(f"  claims recorded:   {len(new)}")
    print(f"  claims now due:    {len(due)}")
    print()

    print("  SOURCE HEALTH")
    for s in states:
        fails = s["fail_count"] or 0
        flag = "  <-- FAILING" if fails > 3 else ""
        last_change = s["last_change"] or "never"
        print(f"    {s['source_id']:<20} polls={s['poll_count']:<5} "
              f"fails={fails:<4} last change {last_change[:10]}{flag}")
    print()

    if new:
        print("  NEW CLAIMS")
        for h in new:
            tr = ledger.track_of(h["category"])
            print(f"    [{h['id']}] {tr}/{h['category']} conf {h['confidence']:.0%} "
                  f"-> resolves {h['resolve_by']}")
            print(f"      {h['claim']}")
            if h["mechanism"]:
                print(f"      why: {h['mechanism']}")
            print()
    else:
        print("  No new claims. If this persists for days with sources healthy,")
        print("  the analyst is correctly declining to manufacture output.")
        print()

    if due:
        print(f"  {len(due)} CLAIM(S) DUE FOR RESOLUTION")
        print("  Run: python ledger.py --due")
        print()

    print("  Paste this whole report into a conversation for review and tuning.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--once", action="store_true", help="one cycle, print, do not record")
    p.add_argument("--daemon", action="store_true", help="run continuously")
    p.add_argument("--report", action="store_true", help="condense recent findings")
    p.add_argument("--hours", type=int, default=24, help="report window (default 24)")
    p.add_argument("--interval", type=int, default=3600,
                   help="daemon sleep between cycles, seconds (default 3600)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    load_dotenv(HERE.parent / ".env")

    if args.report:
        return report(args.hours)

    if args.daemon:
        log.info("daemon start, cycle interval %ds", args.interval)
        log.info("per-source intervals govern actual polling; most sources "
                 "change daily at most")
        while True:
            try:
                result = cycle(dry_run=False)
                log.info("cycle done: %s", result)
            except KeyboardInterrupt:
                log.info("stopped")
                return 0
            except Exception:
                log.exception("cycle failed - continuing")
            time.sleep(args.interval)

    result = cycle(dry_run=args.once)
    log.info("cycle done: %s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
