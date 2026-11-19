#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hmac
import datetime as dt
import json
import os
import sqlite3
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA = ROOT / "data"

sys.path.insert(0, str(HERE))
import ledger
import system_stats
import panel
import health_report
import yaml

load_dotenv(ROOT / ".env")
TOKEN = os.environ.get("WEBUI_TOKEN", "")

app = FastAPI(title="AeroStock", docs_url=None, redoc_url=None)


def load_config() -> dict:
    try:
        return yaml.safe_load((ROOT / "config.yaml").read_text()) or {}
    except Exception:
        return {}


def check_token(token: str | None) -> None:
    if TOKEN and not hmac.compare_digest((token or "").encode(), TOKEN.encode()):
        raise HTTPException(status_code=401, detail="bad or missing token")


def rows(db: Path, query: str, params: tuple = ()) -> list[dict]:
    if not db.exists():
        return []
    try:
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        out = [dict(r) for r in c.execute(query, params).fetchall()]
        c.close()
        return out
    except sqlite3.Error:
        return []


@app.get("/api/status")
def status(token: str | None = Query(None)):
    check_token(token)
    today = dt.date.today().isoformat()

    due = rows(ledger.DB,
               "SELECT COUNT(*) n FROM hypotheses WHERE status='open' AND resolve_by<=?",
               (today,))
    openc = rows(ledger.DB, "SELECT COUNT(*) n FROM hypotheses WHERE status='open'")
    res = rows(ledger.DB, "SELECT COUNT(*) n FROM hypotheses WHERE status='resolved'")

    sources = rows(DATA / "research_state.db",
                   "SELECT source_id, poll_count, fail_count, last_seen, last_change "
                   "FROM source_state ORDER BY source_id")

    last_digest = rows(DATA / "digest_history.db",
                       "SELECT run_at, delivered, generated FROM runs "
                       "ORDER BY run_at DESC LIMIT 1")

    unhealthy = [s["source_id"] for s in sources if (s["fail_count"] or 0) > 3]

    try:
        needs = [i for i in health_report.attention(load_config())
                 if i["severity"] != health_report.INFO]
    except Exception as exc:
        needs = [{"severity": "attention", "key": "health",
                  "text": f"Health check itself failed: {exc}", "fix": ""}]

    return {
        "attention": needs,
        "due": due[0]["n"] if due else 0,
        "open": openc[0]["n"] if openc else 0,
        "resolved": res[0]["n"] if res else 0,
        "sources": sources,
        "unhealthy": unhealthy,
        "last_digest": last_digest[0] if last_digest else None,
        "now": dt.datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/claims")
def claims(which: str = Query("due"), token: str | None = Query(None)):
    check_token(token)
    today = dt.date.today().isoformat()

    if which == "due":
        q = ("SELECT * FROM hypotheses WHERE status='open' AND resolve_by<=? "
             "ORDER BY resolve_by")
        params = (today,)
    elif which == "resolved":
        q = "SELECT * FROM hypotheses WHERE status='resolved' ORDER BY resolved_at DESC LIMIT 50"
        params = ()
    else:
        q = "SELECT * FROM hypotheses WHERE status='open' ORDER BY resolve_by"
        params = ()

    out = rows(ledger.DB, q, params)
    try:
        allf = panel.forecasts_for([r["id"] for r in out]) if out else {}
    except Exception:
        allf = {}
    for r in out:
        fs = dict(allf.get(r["id"], {}))
        r["blend"] = fs.pop(panel.SHOWN, None)
        r["forecasts"] = fs
        r["track"] = ledger.track_of(r["category"])
        try:
            days = (dt.date.fromisoformat(r["resolve_by"]) - dt.date.today()).days
        except (ValueError, TypeError):
            days = None
        r["days_away"] = days
    return out


@app.post("/api/claims/{claim_id}/resolve")
def resolve(claim_id: str, outcome: bool = Query(...),
            note: str = Query(""), token: str | None = Query(None)):
    check_token(token)
    ok = ledger.resolve(claim_id, outcome, note)
    if not ok:
        raise HTTPException(status_code=400,
                            detail="not found, or already resolved")
    return {"ok": True, "id": claim_id, "outcome": outcome}


@app.post("/api/claims/{claim_id}/void")
def void_claim(claim_id: str, note: str = Query(""), token: str | None = Query(None)):
    check_token(token)
    if not ledger.void(claim_id, note):
        raise HTTPException(status_code=400, detail="not found, or already closed")
    return {"ok": True, "id": claim_id, "status": "void"}


DESK_DIR = DATA / "desk"
DESK_LOCK = DESK_DIR / ".running"
TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")


def desk_running() -> bool:
    try:
        return DESK_LOCK.exists() and (time.time() - DESK_LOCK.stat().st_mtime) < 900
    except OSError:
        return False


@app.get("/api/desk")
def desk_list(token: str | None = Query(None)):
    check_token(token)
    briefs = []
    if DESK_DIR.exists():
        for f in sorted(DESK_DIR.glob("*.txt"), reverse=True)[:8]:
            try:
                briefs.append({"name": f.name, "text": f.read_text()})
            except OSError:
                continue
    return {"running": desk_running(), "briefs": briefs}


@app.post("/api/desk/run")
def desk_run(topic: str = Query(...), tickers: str = Query(""),
             token: str | None = Query(None)):
    check_token(token)
    topic = " ".join(topic.split())[:120]
    if len(topic) < 3:
        raise HTTPException(status_code=400, detail="topic too short")
    ticks = [t.upper() for t in re.split(r"[\s,]+", tickers.strip()) if t][:8]
    if any(not TICKER_RE.match(t) for t in ticks):
        raise HTTPException(status_code=400, detail="bad ticker")
    if desk_running():
        raise HTTPException(status_code=409, detail="a brief is already running")

    DESK_DIR.mkdir(parents=True, exist_ok=True)
    DESK_LOCK.write_text(topic)

    cmd = [sys.executable, str(HERE / "event_desk.py"), "--topic", topic]
    if ticks:
        cmd += ["--tickers", *ticks]

    def worker():
        try:
            with open(DESK_DIR / "last-run.log", "w") as logf:
                subprocess.run(cmd, cwd=str(ROOT), stdout=logf,
                               stderr=subprocess.STDOUT, timeout=840)
        except Exception as exc:
            try:
                (DESK_DIR / "last-run.log").write_text(f"desk run failed: {exc}")
            except OSError:
                pass
        finally:
            try:
                DESK_LOCK.unlink()
            except OSError:
                pass

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "topic": topic, "tickers": ticks}


@app.post("/api/desk/ask")
def desk_ask(topic: str = Query(...), tickers: str = Query(""),
             token: str | None = Query(None)):
    check_token(token)
    topic = " ".join(topic.split())[:120]
    if len(topic) < 3:
        raise HTTPException(status_code=400, detail="topic too short")
    ticks = [t.upper() for t in re.split(r"[\s,]+", tickers.strip()) if t][:8]
    if any(not TICKER_RE.match(t) for t in ticks):
        raise HTTPException(status_code=400, detail="bad ticker")
    import event_desk
    try:
        a = event_desk.prepare_ask(topic, ticks, "", load_config())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"could not prepare the ask: {exc}")
    return {"ask_id": a["ask_id"], "topic": a["topic"], "text": a["text"],
            "errors": a["errors"]}


class PastedAnswer(BaseModel):
    ask_id: str
    answer: str


@app.post("/api/desk/import")
def desk_import(body: PastedAnswer, token: str | None = Query(None)):
    check_token(token)
    if len(body.answer) > 200_000:
        raise HTTPException(status_code=413, detail="answer too long")
    import contextlib
    import io
    import event_desk
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        rc = event_desk.import_answer(body.ask_id, body.answer, load_config(), send=True)
    if rc != 0:
        raise HTTPException(status_code=400, detail=err.getvalue().strip() or "import failed")
    return {"ok": True}


@app.get("/api/score")
def score(token: str | None = Query(None)):
    check_token(token)
    resolved = rows(ledger.DB, "SELECT * FROM hypotheses WHERE status='resolved'")

    if len(resolved) < 10:
        return {"enough": False, "resolved": len(resolved),
                "message": f"{len(resolved)} resolved. Scoring needs 10 minimum, "
                           f"30+ before you should believe it."}

    def brier(rs):
        return sum((r["confidence"] - r["outcome"]) ** 2 for r in rs) / len(rs)

    overall = brier(resolved)
    hit = sum(r["outcome"] for r in resolved) / len(resolved)
    conf = sum(r["confidence"] for r in resolved) / len(resolved)

    tracks = []
    for tname in ledger.TRACKS:
        trs = [r for r in resolved if ledger.track_of(r["category"]) == tname]
        if not trs:
            continue
        cats = []
        for cat, (t, _) in ledger.CATEGORIES.items():
            if t != tname:
                continue
            crs = [r for r in trs if r["category"] == cat]
            if crs:
                cats.append({"category": cat, "n": len(crs),
                             "brier": round(brier(crs), 4),
                             "hit_rate": round(sum(r["outcome"] for r in crs) / len(crs), 3)})
        tracks.append({
            "track": tname, "n": len(trs), "brier": round(brier(trs), 4),
            "hit_rate": round(sum(r["outcome"] for r in trs) / len(trs), 3),
            "categories": cats,
        })

    ordered = sorted(resolved, key=lambda r: (r.get("resolved_at") or "", r["id"]))
    try:
        allf = panel.forecasts_for([r["id"] for r in ordered])
    except Exception:
        allf = {}

    timeline, s_loss, p_loss, p_n = [], 0.0, 0.0, 0
    for k, r in enumerate(ordered, 1):
        y = r["outcome"]
        s_loss += (r["confidence"] - y) ** 2
        b = allf.get(r["id"], {}).get(panel.SHOWN)
        if b is not None:
            p_loss += (b - y) ** 2
            p_n += 1
        timeline.append({"k": k, "date": (r.get("resolved_at") or "")[:10],
                         "stated": round(s_loss / k, 4),
                         "panel": round(p_loss / p_n, 4) if p_n else None})
    if len(timeline) > 150:
        step = len(timeline) / 150.0
        timeline = [timeline[int(i * step)] for i in range(150)] + [timeline[-1]]

    def buckets(pairs):
        out = []
        for lo in (0.0, 0.2, 0.4, 0.6, 0.8):
            hi = lo + 0.2
            sel = [(p_, y_) for p_, y_ in pairs if lo <= p_ < hi or (hi >= 1.0 and p_ >= 1.0)]
            if sel:
                out.append({"x": round(sum(p_ for p_, _ in sel) / len(sel), 3),
                            "y": round(sum(y_ for _, y_ in sel) / len(sel), 3),
                            "n": len(sel)})
        return out
    calibration = {
        "stated": buckets([(r["confidence"], r["outcome"]) for r in ordered]),
        "panel": buckets([(allf[r["id"]][panel.SHOWN], r["outcome"]) for r in ordered
                          if panel.SHOWN in allf.get(r["id"], {})]),
    }

    by_basis = []
    for b, desc in ledger.BASIS.items():
        rs = [r for r in resolved if (r.get("basis") or "other") == b]
        if rs:
            by_basis.append({"track": b, "n": len(rs), "brier": round(brier(rs), 4),
                             "hit_rate": round(sum(r["outcome"] for r in rs) / len(rs), 3),
                             "categories": []})

    return {
        "enough": True,
        "by_basis": by_basis,
        "timeline": timeline,
        "calibration": calibration,
        "resolved": len(resolved),
        "brier": round(overall, 4),
        "hit_rate": round(hit, 3),
        "mean_confidence": round(conf, 3),
        "overconfidence": round(conf - hit, 3),
        "tracks": tracks,
    }


@app.get("/api/panel")
def panel_state(token: str | None = Query(None)):
    check_token(token)
    st = panel.compute()
    members = []
    for m in sorted(st["members"], key=lambda x: -st["weights"][x]):
        s_ = st["stats"][m]
        members.append({
            "name": m, "weight": round(st["weights"][m], 4), "n": s_["n"],
            "brier": None if s_["brier"] is None else round(s_["brier"], 4),
            "vs_coin": None if s_["vs_coin"] is None else round(s_["vs_coin"], 4),
            "vs_coin_se": None if s_["vs_coin_se"] is None else round(s_["vs_coin_se"], 4),
            "free": m in panel.FREE,
        })
    n = len(members)
    import math

    hist = st.get("history", [])
    lead = [m["name"] for m in members[:5]]
    if "coin" in st["weights"] and "coin" not in lead:
        lead.append("coin")
    idx = list(range(len(hist)))
    if len(idx) > 120:
        step = len(idx) / 120.0
        idx = sorted({int(i * step) for i in range(120)} | {len(hist) - 1})
    history = {"members": lead,
               "points": [{"k": i + 1, "w": {m: round(hist[i].get(m, 0.0), 4) for m in lead}}
                          for i in idx]}

    return {
        "history": history,
        "members": members,
        "n_resolved": st["n_resolved"],
        "trained": st["trained"],
        "shown": {"n": st["shown"]["n"],
                  "brier": None if st["shown"]["brier"] is None else round(st["shown"]["brier"], 4)},
        "verdict": panel.leader_line(st),
        "bound": round(2 * math.log(n), 1) if n else 0,
    }


@app.get("/api/digests")
def digests(token: str | None = Query(None)):
    check_token(token)
    out = rows(DATA / "digest_history.db",
               "SELECT id, run_at, digest_text, guardrail_hits, data_errors, "
               "delivered, generated FROM runs ORDER BY run_at DESC LIMIT 10")
    for r in out:
        for field in ("guardrail_hits", "data_errors"):
            try:
                r[field] = json.loads(r[field]) if r[field] else []
            except (json.JSONDecodeError, TypeError):
                r[field] = []
    return out


@app.get("/api/texas")
def texas(token: str | None = Query(None)):
    check_token(token)
    try:
        import texas_tracker
        return texas_tracker.snapshot()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"tracker failed: {exc}")


@app.get("/api/calendar")
def calendar(token: str | None = Query(None)):
    check_token(token)
    try:
        r = subprocess.run([sys.executable, str(HERE / "texas_tracker.py"), "--calendar"],
                           capture_output=True, text=True, timeout=30, cwd=str(ROOT))
        return {"ok": r.returncode == 0, "output": r.stdout or r.stderr}
    except Exception as exc:
        return {"ok": False, "output": f"failed: {exc}"}


@app.get("/api/system")
def system(token: str | None = Query(None)):
    check_token(token)
    return system_stats.all_stats()


LOGO_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".webp": "image/webp"}


@app.get("/api/version")
def version(token: str | None = Query(None)):
    check_token(token)
    paths = [ledger.DB, DATA / "research_state.db", DATA / "digest_history.db",
             DATA / "health_state.json", DESK_DIR, DESK_DIR / "last-run.log",
             DESK_DIR / ".running"]
    latest = 0.0
    for p in paths:
        try:
            latest = max(latest, p.stat().st_mtime)
        except OSError:
            continue
    for p in (ledger.DB, DATA / "research_state.db", DATA / "digest_history.db"):
        try:
            latest = max(latest, p.with_name(p.name + "-wal").stat().st_mtime)
        except OSError:
            continue
    return {"v": f"{latest:.3f}"}


STATIC = HERE / "static"


@app.get("/favicon.ico")
def favicon():
    f = STATIC / "favicon.ico"
    if not f.exists():
        raise HTTPException(status_code=404)
    return FileResponse(f, media_type="image/x-icon")


@app.get("/apple-touch-icon.png")
def touch_icon():
    f = STATIC / "apple-touch-icon.png"
    if not f.exists():
        raise HTTPException(status_code=404)
    return FileResponse(f, media_type="image/png")


@app.get("/logo")
def logo():
    for ext, mime in LOGO_TYPES.items():
        f = HERE / "static" / f"logo{ext}"
        if f.exists():
            return FileResponse(f, media_type=mime)
    raise HTTPException(status_code=404, detail="no logo file")


@app.get("/", response_class=HTMLResponse)
def index():
    page = HERE / "static" / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>index.html missing</h1>", status_code=500)
    return HTMLResponse(page.read_text())


@app.exception_handler(HTTPException)
def http_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


if __name__ == "__main__":
    import uvicorn
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--allow-no-token", action="store_true")
    a = p.parse_args()

    if a.host not in ("127.0.0.1", "localhost", "::1") and not TOKEN:
        if not a.allow_no_token:
            sys.exit(f"Refusing to listen on {a.host} without WEBUI_TOKEN set. "
                     "Set it in .env, or pass --allow-no-token on a network you trust.")
        print("WARNING: listening with no token. Never expose this port to the internet.", file=sys.stderr)

    uvicorn.run(app, host=a.host, port=a.port, log_level="info")
