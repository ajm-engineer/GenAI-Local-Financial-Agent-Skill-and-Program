#!/usr/bin/env python3

import base64
import json
import math
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
PAGE = ROOT / "scripts" / "static" / "index.html"


def tool_output(*args: str) -> str:
    try:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "texas_tracker.py"), *args],
                           capture_output=True, text=True, timeout=30, cwd=str(ROOT))
        return r.stdout.strip() or "(no output)"
    except Exception as exc:
        return f"(could not run the tracker: {exc})"


SYSTEM = {
    "power": {"has_battery": True, "on_ac": True, "percent": 100, "status": "Full",
              "health_pct": 71, "minutes_left": None},
    "thermals": {"cpu_c": 58.0, "zones": []},
    "gpu": {"available": True, "name": "NVIDIA GeForce RTX 4060 Laptop GPU", "temp_c": 49.0,
            "util_pct": 3.0, "memory_used_mb": 5890.0, "memory_total_mb": 8192.0,
            "memory_pct": 72, "power_w": 18.0, "model_loaded": True},
    "host": {"uptime": "12d 4h 31m", "load": [0.38, 0.41, 0.36], "cpus": 20,
             "mem_total_mb": 31880, "mem_used_mb": 9120, "mem_pct": 29,
             "disk_total_gb": 467.9, "disk_used_gb": 88.4, "disk_pct": 19},
    "network": {
        "interfaces": [
            {"name": "enp2s0", "kind": "ethernet", "state": "UP", "ipv4": ["192.0.2.40"],
             "is_default": True, "speed_mbps": 1000},
            {"name": "wlp1s0", "kind": "wifi", "state": "UP", "ipv4": ["192.0.2.57"],
             "is_default": False, "ssid": "example-wifi", "signal_dbm": -58, "signal_quality": "good"}],
        "tailscale": {"online": True, "ips": ["100.64.0.10"], "peers": 2, "state": "Running"}},
    "services": {"ollama": "active", "research-loop": "active", "market-digest-web": "active",
                 "tailscaled": "active", "ssh": "active"},
    "collected_at": "2026-11-15 18:02:11",
}

DIGEST_1 = """Scheduled: NVDA reports earnings on 2026-11-17, 2 days away. Anthropic is
expected to price its IPO on 2026-11-18 and begin trading on 2026-11-19.

Notable moves: NVDA closed at 173.73, up 2.87% from 168.89. AMD closed up 1.7%.

Macro: the 10-year Treasury yield was 4.96%, down 4 bps.

Filings: NVDA filed a Form 8-K on 2026-11-10.

Mechanics: the sessions just before an earnings report often trade in a wider
range than usual. That says nothing about direction."""


def fc(primary, **more):
    import math
    def clamp(p): return min(max(p, 0.02), 0.98)
    lg = math.log(clamp(primary) / (1 - clamp(primary)))
    d = {"coin": 0.5, "base_rate": 0.5, "primary": primary,
         "primary_shrunk": 0.5 + (primary - 0.5) / 2,
         "primary_sharp": clamp(1 / (1 + math.exp(-1.5 * lg)))}
    d.update(more)
    return d


def claim(cid, text, cat, track, conf, by, days, why="", blend=None, **more):
    f = fc(conf, **more)
    if blend is None:
        blend = sum(f.values()) / len(f)
    return {"id": cid, "claim": text, "category": cat, "track": track, "confidence": conf,
            "resolve_by": by, "days_away": days, "mechanism": why, "status": "open",
            "blend": round(blend, 3), "forecasts": {k: round(v, 3) for k, v in f.items()}}


SAMPLE_DESK = [
    claim("c8958dae", "Northwind's current CEO is no longer CEO on 2026-12-01", "event", "desk", 0.75,
          "2026-12-01", 16, "Board went from stated confidence to a removal meeting in three days and engaged a search firm.",
          outside=0.45, inside=0.78, skeptic=0.55),
    claim("3b301019", "Northwind announces a named interim or permanent successor CEO on or before 2026-12-01",
          "event", "desk", 0.55, "2026-12-01", 16, "Reports say the board was considering a temporary chief.",
          outside=0.40, inside=0.62, skeptic=0.45),
    claim("6dd04e38", "IF Northwind announces its CEO stays or moves to a chairman role THEN NWND closes higher on the next regular session than the prior close, by 2026-12-01",
          "reaction", "desk", 0.80, "2026-12-01", 16, "The stock had priced roughly half of a full no-CEO discount.",
          outside=0.60, inside=0.74, skeptic=0.58),
]

DAY_ONE = {
    "label": "Day one: just installed, nothing graded yet",
    "status": {"attention": [], "open": 3, "resolved": 0, "now": "2026-11-15T18:02:00"},
    "claims": SAMPLE_DESK,
    "score": {"enough": False, "resolved": 0,
              "message": "0 resolved. Scoring needs 10 minimum, 30+ before you should believe it."},
    "panel": {
        "members": [{"name": n, "weight": 0.125, "n": 0, "brier": None, "vs_coin": None,
                     "vs_coin_se": None, "free": n not in ("outside", "inside", "skeptic")}
                    for n in ("coin", "base_rate", "primary", "primary_shrunk", "primary_sharp",
                              "outside", "inside", "skeptic")],
        "n_resolved": 0, "trained": False, "shown": {"n": 0, "brier": None},
        "verdict": "Panel: 8 members, 0 claim(s) resolved. Untrained, so the blend is a plain average.",
        "bound": 4.2},
    "briefs": [],
    "digests": [{"run_at": "2026-11-13T07:31:04", "digest_text": DIGEST_1,
                 "guardrail_hits": [], "data_errors": [], "generated": True}],
    "system": SYSTEM,
}

BRIEF = """EVENT DESK: Northwind CEO succession (fictional)
2027-02-08 19:14   model: anthropic/claude-sonnet-5-5
Track record: 14 desk calls resolved, 9 correct, Brier 0.229 (within noise; 0.25 = coin flip).

SUMMARY
(sample text) The interim chief has held the role for ten weeks. What decides
the next move is the board's permanent appointment and the guidance on the
February report.

SCENARIOS
  50%  Interim confirmed as permanent
       Removes the open question; the reaction depends on guidance.
  35%  Outside hire announced
       A fresh strategy review; wider range of outcomes.
  15%  Search continues past the quarter
       The uncertainty discount stays in place.

WHAT'S PRICED
Not computable from the available facts.

SETUPS (ranked by soundness of logic, not by upside)
 1. Wait for the appointment and the report [NWND]
    why: two binary events fall inside the next ten days
    fails if: the stock gaps before you act and you miss the first move

TRAPS
 - Short-dated options into the report: prices collapse after the print.

UNKNOWNS (would change these odds)
 - Whether the board has already made an offer.

LOGGED FOR GRADING (desk's odds, then the panel's blend)
 - [a41f0c22] desk 50%, panel 47% by 2027-03-15: Northwind names its interim CEO as permanent CEO on or before 2027-03-15
 Panel: after 41 resolved claims the top-weighted member is 'outside' with 22% of the weight.

Sizing is yours. Nothing above is certain, and every call is graded."""

IN_USE_CLAIMS = [
    claim("d17a90b3", "ERCOT grants Approval to Energize to at least 3 of the 17 paused projects on or before 2027-02-05",
          "approval", "texas", 0.35, "2027-02-05", -3, "The PUCT acted on the verification report in January.",
          blend=0.31, outside=0.25, inside=0.40, skeptic=0.22, analyst_raw=0.85),
    claim("e52c7714", "IF Nvidia guides non-GAAP gross margin below 70% in its February report THEN AMD closes higher on the next regular session than the prior close, by 2027-02-27",
          "reaction", "desk", 0.60, "2027-02-06", -2, "A margin cut would be read as pricing pressure from alternatives.",
          blend=0.53, outside=0.50, inside=0.62, skeptic=0.45),
    claim("f09b3d58", "Oracle Cloud Infrastructure lists TPU instances as generally available on or before 2027-02-08",
          "adoption", "silicon", 0.20, "2027-02-08", 0, "Oracle said 2027 without naming a quarter.",
          blend=0.19, outside=0.15, inside=0.24, skeptic=0.12, analyst_raw=0.80),
    claim("a41f0c22", "Northwind names its interim CEO as permanent CEO on or before 2027-03-15",
          "event", "desk", 0.50, "2027-03-15", 35, "", blend=0.47, outside=0.42, inside=0.55, skeptic=0.40, market=0.44),
    claim("b7e81f06", "The Texas Legislature passes a bill containing a data center moratorium out of at least one chamber on or before 2027-04-30",
          "policy", "texas", 0.30, "2027-04-30", 81, "The governor campaigned on it; the legislature is not hers.",
          blend=0.27, outside=0.18, inside=0.36, skeptic=0.22, analyst_raw=0.85),
    claim("c3390aa1", "Nvidia reports data center revenue above $95 billion for the quarter in its report published before 2027-03-01",
          "pricing", "silicon", 0.65, "2027-03-01", 21, "", blend=0.58, outside=0.55, inside=0.66, skeptic=0.50, analyst_raw=0.90),
]

IN_USE = {
    "label": "In use: invented data, as it might look after about three months",
    "status": {"attention": [
        {"severity": "attention", "key": "sources", "text": "Sources failing: tceq_permits.",
         "fix": "A failing source quietly narrows what the loop can see."}],
        "open": 6, "resolved": 41, "now": "2027-02-08T19:20:00"},
    "claims": IN_USE_CLAIMS,
    "score": {"enough": True, "resolved": 41, "brier": 0.2141, "hit_rate": 0.561,
              "mean_confidence": 0.612, "overconfidence": 0.051,
              "tracks": [
                  {"track": "texas", "n": 18, "brier": 0.1874, "hit_rate": 0.444, "categories": [
                      {"category": "approval", "n": 9, "brier": 0.1702, "hit_rate": 0.333},
                      {"category": "bottleneck", "n": 5, "brier": 0.1911, "hit_rate": 0.6},
                      {"category": "policy", "n": 4, "brier": 0.2215, "hit_rate": 0.5}]},
                  {"track": "silicon", "n": 9, "brier": 0.2433, "hit_rate": 0.556, "categories": [
                      {"category": "moat", "n": 3, "brier": 0.2288, "hit_rate": 0.333},
                      {"category": "adoption", "n": 3, "brier": 0.2104, "hit_rate": 0.667},
                      {"category": "pricing", "n": 3, "brier": 0.2907, "hit_rate": 0.667}]},
                  {"track": "desk", "n": 14, "brier": 0.2296, "hit_rate": 0.714, "categories": [
                      {"category": "event", "n": 8, "brier": 0.1713, "hit_rate": 0.75},
                      {"category": "reaction", "n": 4, "brier": 0.3050, "hit_rate": 0.5},
                      {"category": "setup", "n": 2, "brier": 0.3120, "hit_rate": 1.0}]}]},
    "panel": {
        "members": [
            {"name": "outside", "weight": 0.22, "n": 39, "brier": 0.1811, "vs_coin": -0.0689, "vs_coin_se": 0.0301, "free": False},
            {"name": "primary_shrunk", "weight": 0.17, "n": 41, "brier": 0.1984, "vs_coin": -0.0516, "vs_coin_se": 0.0212, "free": True},
            {"name": "skeptic", "weight": 0.14, "n": 38, "brier": 0.2050, "vs_coin": -0.0450, "vs_coin_se": 0.0340, "free": False},
            {"name": "primary", "weight": 0.11, "n": 41, "brier": 0.2141, "vs_coin": -0.0359, "vs_coin_se": 0.0398, "free": True},
            {"name": "inside", "weight": 0.10, "n": 39, "brier": 0.2190, "vs_coin": -0.0310, "vs_coin_se": 0.0377, "free": False},
            {"name": "base_rate", "weight": 0.09, "n": 41, "brier": 0.2422, "vs_coin": -0.0078, "vs_coin_se": 0.0101, "free": True},
            {"name": "coin", "weight": 0.08, "n": 41, "brier": 0.25, "vs_coin": None, "vs_coin_se": None, "free": True},
            {"name": "market", "weight": 0.05, "n": 6, "brier": 0.1640, "vs_coin": -0.0860, "vs_coin_se": 0.0710, "free": False},
            {"name": "primary_sharp", "weight": 0.03, "n": 41, "brier": 0.2619, "vs_coin": 0.0119, "vs_coin_se": 0.0502, "free": True},
            {"name": "analyst_raw", "weight": 0.01, "n": 27, "brier": 0.3377, "vs_coin": 0.0877, "vs_coin_se": 0.0333, "free": False}],
        "n_resolved": 41, "trained": True, "shown": {"n": 41, "brier": 0.2012},
        "verdict": "Panel: after 41 resolved claims the top-weighted member is 'outside' with 22% of the weight.",
        "bound": 4.6},
    "briefs": [{"name": "20270208-1914-northwind-ceo-succession.txt", "text": BRIEF}],
    "digests": [{"run_at": "2027-02-08T07:31:12", "digest_text": DIGEST_1.replace("2026-11", "2027-02"),
                 "guardrail_hits": [], "data_errors": [], "generated": True},
                {"run_at": "2027-02-05T07:30:48", "digest_text": "Nothing on the watchlist moved more than its threshold, and nothing is scheduled in the next two weeks. A quiet day.",
                 "guardrail_hits": [], "data_errors": [], "generated": True}],
    "system": {**SYSTEM, "collected_at": "2027-02-08 19:20:03"},
}

def sample_series() -> None:
    rng = random.Random(41)
    n = 41

    timeline, s_run, p_run = [], 0.0, 0.0
    for k in range(1, n + 1):
        s_run += max(0.0, rng.gauss(0.2141, 0.19))
        p_run += max(0.0, rng.gauss(0.2012, 0.15))
        timeline.append({"k": k, "date": "", "stated": round(s_run / k, 4),
                         "panel": round(p_run / k, 4)})
    timeline[-1]["stated"], timeline[-1]["panel"] = 0.2141, 0.2012
    IN_USE["score"]["timeline"] = timeline

    IN_USE["score"]["by_basis"] = [
        {"track": "unread_source", "n": 16, "brier": 0.1712, "hit_rate": 0.44, "categories": []},
        {"track": "scheduled", "n": 9, "brier": 0.1890, "hit_rate": 0.67, "categories": []},
        {"track": "headline", "n": 13, "brier": 0.2694, "hit_rate": 0.62, "categories": []},
        {"track": "market", "n": 3, "brier": 0.1420, "hit_rate": 0.67, "categories": []}]
    for c, b in zip(IN_USE["claims"], ["unread_source", "headline", "unread_source", "headline", "scheduled", "unread_source"]):
        c["basis"] = b
    for c in DAY_ONE["claims"]:
        c["basis"] = "headline"

    IN_USE["score"]["calibration"] = {
        "stated": [{"x": 0.28, "y": 0.33, "n": 9}, {"x": 0.50, "y": 0.47, "n": 8},
                   {"x": 0.69, "y": 0.60, "n": 15}, {"x": 0.86, "y": 0.67, "n": 9}],
        "panel": [{"x": 0.33, "y": 0.33, "n": 12}, {"x": 0.52, "y": 0.50, "n": 16},
                  {"x": 0.66, "y": 0.69, "n": 13}],
    }

    final = {m["name"]: m["weight"] for m in IN_USE["panel"]["members"]}
    lead = ["outside", "primary_shrunk", "skeptic", "primary", "inside", "coin"]
    start = 1.0 / len(final)
    points = []
    for k in range(1, n + 1):
        t = (k / n) ** 1.6
        w = {m: round(start + (final[m] - start) * t + rng.gauss(0, 0.004) * (1 - t), 4)
             for m in lead}
        points.append({"k": k, "w": w})
    points[-1]["w"] = {m: final[m] for m in lead}
    IN_USE["panel"]["history"] = {"members": lead, "points": points}

    DAY_ONE["panel"]["history"] = {"members": [], "points": []}


def logo_data_uri() -> str | None:
    types = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
             ".jpeg": "image/jpeg", ".webp": "image/webp"}
    for ext, mime in types.items():
        f = ROOT / "scripts" / "static" / f"logo{ext}"
        if f.exists():
            return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()
    return None


MOCK_JS = r"""
<script>
/* PREVIEW ONLY. Replaces the page's network calls with sample data. */
(function () {
  const D = __DATA__;
  const reply = (body, status) => Promise.resolve({ ok: !status || status < 400, status: status || 200, json: async () => body });
  const due = () => D.claims.filter(c => c.status === 'open' && c.days_away <= 0);
  window.fetch = function (url, opts) {
    const u = new URL(url, 'http://box.local');
    const path = u.pathname, method = (opts && opts.method) || 'GET';
    let m;
    if (path === '/api/status') return reply({ ...D.status, due: due().length,
      open: D.claims.filter(c => c.status === 'open').length });
    if (path === '/api/claims') {
      const w = u.searchParams.get('which');
      return reply(w === 'due' ? due() : D.claims.filter(c => c.status === 'open'));
    }
    if ((m = path.match(/^\/api\/claims\/(\w+)\/(resolve|void)$/)) && method === 'POST') {
      const c = D.claims.find(x => x.id === m[1]);
      if (!c || c.status !== 'open') return reply({ error: 'not found, or already resolved' }, 400);
      c.status = m[2] === 'void' ? 'void' : 'resolved';
      if (m[2] === 'resolve') D.status.resolved += 1;
      return reply({ ok: true });
    }
    if (path === '/api/score') return reply(D.score);
    if (path === '/api/panel') return reply(D.panel);
    if (path === '/api/desk') return reply({ running: false, briefs: D.briefs });
    if (path === '/api/desk/run') return reply({ ok: true });
    if (path === '/api/digests') return reply(D.digests);
    if (path === '/api/texas') return reply(D.texas);
    if (path === '/api/desk/ask') return reply({ ask_id: '20261113-120000', topic: 'sample', text: 'PREVIEW: the real request would be here.', errors: [] });
    if (path === '/api/desk/import') return reply({ error: 'not in the preview' }, 400);
    if (path === '/api/calendar') return reply({ ok: true, output: D.calendar });
    if (path === '/api/system') return reply(D.system);
    if (path === '/api/version') return reply({ v: '1' });
    return reply({ error: 'not in the preview' }, 404);
  };
})();
</script>
"""

BANNER = """<div style="background:#A66B10;color:#fff;font:600 14px system-ui,sans-serif;padding:9px 14px;text-align:center">
Preview with made-up sample data. Nothing on this page is a real result. __LABEL__</div>
"""


def build(data: dict, out: Path) -> None:
    page = PAGE.read_text()
    import json as _json
    data = {**data, "texas": _json.loads(tool_output("--json")), "calendar": tool_output("--calendar", "--horizon", "400")}
    label = data.pop("label")
    mock = MOCK_JS.replace("__DATA__", json.dumps(data))
    marker = "<script>\nconst TOKEN"
    if marker not in page:
        sys.exit("page layout changed: could not find where to inject the sample data")
    page = page.replace(marker, mock + marker, 1)
    page = page.replace("<body>", "<body>\n" + BANNER.replace("__LABEL__", label), 1)
    page = page.replace("<title>AeroStock</title>", "<title>AeroStock preview</title>", 1)
    uri = logo_data_uri()
    if uri:
        page = page.replace('<img id="logo" src="logo"', f'<img id="logo" src="{uri}"', 1)
    ico = ROOT / "scripts" / "static" / "favicon.ico"
    if ico.exists():
        page = page.replace('href="favicon.ico"',
                            'href="data:image/x-icon;base64,' + base64.b64encode(ico.read_bytes()).decode() + '"', 1)
    page = page.replace('<link rel="apple-touch-icon" href="apple-touch-icon.png">', '', 1)
    out.write_text(page)
    print(f"wrote {out}  ({len(page):,} bytes)")


if __name__ == "__main__":
    sample_series()
    build(DAY_ONE, HERE / "preview-day-one.html")
    build(IN_USE, HERE / "preview-in-use.html")
