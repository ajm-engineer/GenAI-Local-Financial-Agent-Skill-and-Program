#!/usr/bin/env python3
"""Export an audit bundle with everything needed to analyse the system elsewhere.

    python export_audit.py                  # data/exports/audit-YYYYMMDD-HHMM.zip
    python export_audit.py --send           # also send it to Telegram
    python export_audit.py --out /mnt/usb
    python export_audit.py --keep 12
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import ledger

EXPORTS = ROOT / "data" / "exports"
HOLDOUT_DAYS = 30


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(out_dir: Path, keep: int) -> Path:
    if not ledger.DB.exists():
        raise SystemExit("No ledger yet, nothing to export.")
    ledger.conn().close()

    now = dt.datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"audit-{stamp}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db_copy = tmp / "ledger.db"
        src = sqlite3.connect(ledger.DB)
        dst = sqlite3.connect(db_copy)
        with dst:
            src.backup(dst)
        src.close()

        c = sqlite3.connect(db_copy)
        counts = {
            "claims": c.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0],
            "graded": c.execute("SELECT COUNT(*) FROM hypotheses WHERE status='resolved'").fetchone()[0],
            "void": c.execute("SELECT COUNT(*) FROM hypotheses WHERE status='void'").fetchone()[0],
            "open": c.execute("SELECT COUNT(*) FROM hypotheses WHERE status='open'").fetchone()[0],
            "forecasts": c.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0],
            "snapshots": c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
            "input_records": c.execute("SELECT COUNT(*) FROM claim_inputs").fetchone()[0],
            "claims_without_snapshot": c.execute(
                "SELECT COUNT(*) FROM hypotheses h WHERE NOT EXISTS "
                "(SELECT 1 FROM claim_inputs i WHERE i.claim_id = h.id)").fetchone()[0],
        }
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.close()

        questions = ROOT / "references" / "audit-questions.md"
        if questions.exists():
            shutil.copy(questions, tmp / "questions.md")

        manifest = {
            "created_at": now.isoformat(timespec="seconds"),
            "holdout_from": (now - dt.timedelta(days=HOLDOUT_DAYS)).date().isoformat(),
            "holdout_rule": f"calls graded on or after holdout_from are held out; "
                            f"answer the questions on older calls, then check on these",
            "counts": counts,
            "integrity_check": integrity,
            "files": {p.name: sha256(p) for p in sorted(tmp.iterdir())},
        }
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2))

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(tmp.iterdir()):
                z.write(p, arcname=p.name)

    bundles = sorted(list(out_dir.glob("audit-*.zip")) + list(out_dir.glob("audit-*.tar.gz")))
    for old in bundles[:-keep] if keep > 0 else []:
        old.unlink()

    print(f"Wrote {target} ({target.stat().st_size / 1024:.0f} KB)")
    print(f"  {counts['graded']} graded, {counts['open']} open, {counts['void']} void, "
          f"{counts['snapshots']} snapshots; integrity: {integrity}")
    if counts["claims_without_snapshot"]:
        print(f"  {counts['claims_without_snapshot']} call(s) have no input record "
              f"(made before snapshots existed, or a snapshot failed).")
    print("  Copy it off the box: scp user@your-server:" + str(target) + " .")
    return target


def latest_age_days() -> float | None:
    bundles = sorted(list(EXPORTS.glob("audit-*.zip")) + list(EXPORTS.glob("audit-*.tar.gz")),
                     key=lambda p: p.stat().st_mtime)
    if not bundles:
        return None
    return (dt.datetime.now().timestamp() - bundles[-1].stat().st_mtime) / 86400


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(EXPORTS), help="directory to write to")
    p.add_argument("--keep", type=int, default=6, help="bundles to keep in that directory")
    p.add_argument("--send", action="store_true",
                   help="also send the bundle to your Telegram chat as a file")
    args = p.parse_args()
    target = export(Path(args.out), args.keep)
    if args.send:
        from dotenv import load_dotenv
        import notify
        load_dotenv(ROOT / ".env")
        c = sqlite3.connect(ledger.DB)
        graded = c.execute("SELECT COUNT(*) FROM hypotheses WHERE status='resolved'").fetchone()[0]
        c.close()
        ok = notify.send_file(target, f"AeroStock audit bundle, {graded} graded calls. "
                              f"Save this somewhere off the box; it is also the ledger backup. "
                              f"Analyse with: python analyze_audit.py {target.name}")
        print("Sent to Telegram." if ok else "Telegram send failed; the bundle is still on disk.")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
