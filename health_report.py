#!/usr/bin/env python3
"""Box health: a weekly Telegram summary and alerts when something needs attention.

    python health_report.py --print
    python health_report.py --weekly
    python health_report.py --check
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA = ROOT / "data"
STATE = DATA / "health_state.json"

sys.path.insert(0, str(HERE))
import ledger
import notify
import system_stats

URGENT, ATTENTION, INFO = "urgent", "attention", "info"

DEFAULTS = {
    "cpu_temp_warn_c": 85, "disk_warn_pct": 85, "ram_warn_pct": 90,
    "battery_health_warn_pct": 60, "loop_stalled_hours": 6,
    "services": ["ollama", "research-loop", "market-digest-web", "tailscaled", "ssh"],
    "repeat_urgent_hours": 6, "repeat_attention_hours": 24,
}


def settings(config: dict) -> dict:
    return {**DEFAULTS, **(config.get("health") or {})}


def _rows(db: Path, query: str, params: tuple = ()) -> list[sqlite3.Row]:
    if not db.exists():
        return []
    try:
        c = sqlite3.connect(db)
        c.row_factory = sqlite3.Row
        out = c.execute(query, params).fetchall()
        c.close()
        return out
    except sqlite3.Error:
        return []


def pipeline() -> dict:
    today = dt.date.today().isoformat()
    week_ago = (dt.datetime.now() - dt.timedelta(days=7)).isoformat()

    counts = {r["status"]: r["n"] for r in _rows(
        ledger.DB, "SELECT status, COUNT(*) n FROM hypotheses GROUP BY status")}
    due = _rows(ledger.DB,
                "SELECT resolve_by FROM hypotheses WHERE status='open' AND resolve_by<=? "
                "ORDER BY resolve_by", (today,))
    oldest = None
    if due:
        try:
            oldest = (dt.date.today() - dt.date.fromisoformat(due[0]["resolve_by"])).days
        except ValueError:
            pass

    state_db = DATA / "research_state.db"
    cycles = _rows(state_db,
                   "SELECT COUNT(*) n, COALESCE(SUM(changes),0) ch, "
                   "COALESCE(SUM(hypotheses),0) hy FROM cycles WHERE ran_at>=?", (week_ago,))
    last_cycle = _rows(state_db, "SELECT MAX(ran_at) t FROM cycles")
    last_poll = _rows(state_db, "SELECT MAX(last_seen) t FROM source_state")
    failing = [r["source_id"] for r in _rows(
        state_db, "SELECT source_id FROM source_state WHERE fail_count > 3")]
    last_digest = _rows(DATA / "digest_history.db", "SELECT MAX(run_at) t FROM runs")

    def hours_since(rows) -> float | None:
        t = rows[0]["t"] if rows and rows[0]["t"] else None
        if not t:
            return None
        try:
            return (dt.datetime.now() - dt.datetime.fromisoformat(t)).total_seconds() / 3600
        except ValueError:
            return None

    return {
        "open": counts.get("open", 0), "resolved": counts.get("resolved", 0),
        "void": counts.get("void", 0), "due": len(due), "oldest_due_days": oldest,
        "cycles_7d": cycles[0]["n"] if cycles else 0,
        "changes_7d": cycles[0]["ch"] if cycles else 0,
        "claims_7d": cycles[0]["hy"] if cycles else 0,
        "hours_since_poll": hours_since(last_poll),
        "hours_since_cycle": hours_since(last_cycle),
        "hours_since_digest": hours_since(last_digest),
        "failing_sources": failing,
    }


def attention(config: dict, stats: dict | None = None,
              pipe: dict | None = None) -> list[dict]:
    s = settings(config)
    stats = stats or system_stats.all_stats()
    pipe = pipe or pipeline()
    items: list[dict] = []

    def add(sev: str, key: str, text: str, fix: str = "") -> None:
        items.append({"severity": sev, "key": key, "text": text, "fix": fix})

    p = stats.get("power", {})
    if p.get("has_battery") and (p.get("status") == "Discharging" or p.get("on_ac") is False):
        left = f", about {p['minutes_left']} min left" if p.get("minutes_left") else ""
        pct = f" at {p['percent']}%" if p.get("percent") is not None else ""
        add(URGENT, "on_battery", f"Running on battery{pct}{left}.",
            "Check the charger and the wall socket.")
    if p.get("health_pct") is not None and p["health_pct"] < s["battery_health_warn_pct"]:
        add(INFO, "battery_health",
            f"Battery holds {p['health_pct']}% of its design capacity.",
            "It will not carry the box far through a power cut. Nothing to do "
            "unless outages are common.")

    cpu = (stats.get("thermals") or {}).get("cpu_c")
    if cpu is not None and cpu >= s["cpu_temp_warn_c"]:
        add(URGENT, "cpu_temp", f"CPU at {cpu:.0f}°C.",
            "Is the lid shut on a soft surface, or the vents blocked?")
    h = stats.get("host", {})
    if h.get("disk_pct") is not None and h["disk_pct"] >= s["disk_warn_pct"]:
        sev = URGENT if h["disk_pct"] >= 95 else ATTENTION
        add(sev, "disk", f"Disk {h['disk_pct']}% full.",
            "Old Ollama models are the usual culprit: `ollama list`, then `ollama rm`.")
    if h.get("mem_pct") is not None and h["mem_pct"] >= s["ram_warn_pct"]:
        add(ATTENTION, "ram", f"Memory {h['mem_pct']}% used.")

    g = stats.get("gpu", {})
    if not g.get("available"):
        add(ATTENTION, "gpu", "The GPU is not responding to nvidia-smi.",
            "Ollama will be running on the CPU, about ten times slower. Usually a "
            "driver that did not survive a kernel update: reboot, then check `nvidia-smi`.")

    svc = stats.get("services", {})
    for name in s["services"]:
        state = svc.get(name, "unknown")
        if state == "failed":
            add(URGENT, f"svc_{name}", f"Service {name} has failed.",
                f"`journalctl -u {name} -n 50` then `sudo systemctl restart {name}`.")
        elif state not in ("active", "unknown", "activating"):
            add(ATTENTION, f"svc_{name}", f"Service {name} is {state}.",
                f"`sudo systemctl start {name}`")

    net = stats.get("network", {})
    ts = net.get("tailscale")
    if ts is not None and not ts.get("online"):
        add(ATTENTION, "tailscale", "Tailscale is offline.",
            "You can only reach the box from the home network until it is back.")

    hp = pipe.get("hours_since_poll")
    if hp is not None and hp > s["loop_stalled_hours"]:
        add(URGENT, "loop_stalled",
            f"The research loop has not polled a source in {hp:.0f} hours.",
            "`sudo systemctl status research-loop`")
    if pipe.get("failing_sources"):
        add(ATTENTION, "sources",
            "Sources failing: " + ", ".join(pipe["failing_sources"]) + ".",
            "A failing source quietly narrows what the loop can see.")
    hd = pipe.get("hours_since_digest")
    if hd is not None and hd > 96:
        add(ATTENTION, "digest", f"No morning digest for {hd / 24:.0f} days.",
            "`systemctl list-timers | grep market-digest`")
    if pipe.get("due"):
        late = pipe.get("oldest_due_days") or 0
        add(ATTENTION, "due",
            f"{pipe['due']} call(s) waiting to be graded"
            + (f", the oldest {late} days overdue." if late > 0 else "."),
            "Open the Grade tab. Ungraded calls are the one thing that stops "
            "the system learning.")

    try:
        import export_audit
        age = export_audit.latest_age_days()
        if pipe.get("resolved", 0) + pipe.get("open", 0) >= 10 and (age is None or age > 40):
            add(ATTENTION, "export",
                "No audit export in over 40 days." if age else "No audit export yet.",
                "`python scripts/export_audit.py --send` sends it to Telegram. "
                "It is also the only backup of the ledger.")
    except Exception:
        pass

    if Path("/var/run/reboot-required").exists():
        add(ATTENTION, "reboot", "Ubuntu wants a reboot to finish updates.",
            "`sudo reboot` when nothing is mid-run.")

    rank = {URGENT: 0, ATTENTION: 1, INFO: 2}
    items.sort(key=lambda i: rank[i["severity"]])
    return items


def weekly_text(config: dict) -> str:
    stats = system_stats.all_stats()
    pipe = pipeline()
    items = attention(config, stats, pipe)
    h, p, g = stats.get("host", {}), stats.get("power", {}), stats.get("gpu", {})
    t, net = stats.get("thermals", {}), stats.get("network", {})

    L = [f"AEROSTOCK BOX REPORT, week ending {dt.date.today().isoformat()}", ""]

    todo = [i for i in items if i["severity"] != INFO]
    info = [i for i in items if i["severity"] == INFO]
    if todo:
        L.append("NEEDS YOU")
        for i in todo:
            mark = "!!" if i["severity"] == URGENT else " -"
            L.append(f"{mark} {i['text']}")
            if i["fix"]:
                L.append(f"     {i['fix']}")
    else:
        L.append("Nothing needs you this week.")
    if info:
        L.append("")
        L.append("WORTH KNOWING")
        for i in info:
            L.append(f" - {i['text']} {i['fix']}".rstrip())
    L.append("")

    L.append("MACHINE")
    L.append(f"  Up {h.get('uptime', '?')}, load {h.get('load', ['?'])[0]} on {h.get('cpus', '?')} cores")
    temp = f"CPU {t['cpu_c']:.0f}°C" if t.get("cpu_c") is not None else "CPU temp unknown"
    if g.get("available") and g.get("temp_c") is not None:
        temp += f", GPU {g['temp_c']:.0f}°C"
    L.append(f"  {temp}")
    if h.get("mem_pct") is not None:
        L.append(f"  Memory {h['mem_pct']}%, disk {h.get('disk_pct', '?')}% "
                 f"({h.get('disk_used_gb', '?')} of {h.get('disk_total_gb', '?')} GB)")
    if g.get("available"):
        loaded = "model loaded" if g.get("model_loaded") else "no model in memory right now"
        L.append(f"  GPU memory {g.get('memory_used_mb', 0):.0f} of "
                 f"{g.get('memory_total_mb', 0):.0f} MB, {loaded}")
    if p.get("has_battery"):
        health = f", holds {p['health_pct']}% of design capacity" if p.get("health_pct") is not None else ""
        src = "on mains" if p.get("on_ac") else "ON BATTERY"
        L.append(f"  Battery {p.get('percent', '?')}% ({src}){health}")
    up = [i for i in net.get("interfaces", []) if i.get("state") == "UP" and i.get("ipv4")]
    if up:
        via = next((i for i in up if i.get("is_default")), up[0])
        sig = f", signal {via['signal_quality']}" if via.get("signal_quality") else ""
        L.append(f"  Online through {via['name']} ({via['kind']}{sig})")
    ts = net.get("tailscale")
    if ts:
        L.append(f"  Tailscale {'connected' if ts.get('online') else 'OFFLINE'}")
    L.append("")

    L.append("PIPELINE, last 7 days")
    alive = pipe.get("hours_since_poll")
    L.append("  Research loop last polled "
             + (f"{alive:.1f} hours ago" if alive is not None else "never (not started yet)"))
    L.append(f"  {pipe['cycles_7d']} cycle(s) found changes, {pipe['claims_7d']} claim(s) logged")
    L.append(f"  Ledger: {pipe['open']} open, {pipe['due']} due, "
             f"{pipe['resolved']} graded, {pipe['void']} void")
    if pipe["resolved"] < 30:
        L.append(f"  {30 - pipe['resolved']} more graded calls before the scores mean much")
    return "\n".join(L)


def alert_text(items: list[dict]) -> str:
    urgent = any(i["severity"] == URGENT for i in items)
    L = ["AEROSTOCK ALERT" if urgent else "AeroStock box needs attention", ""]
    for i in items:
        L.append(("!! " if i["severity"] == URGENT else "- ") + i["text"])
        if i["fix"]:
            L.append(f"   {i['fix']}")
    return "\n".join(L)


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))


def check(config: dict, send: bool = True) -> int:
    s = settings(config)
    items = [i for i in attention(config) if i["severity"] != INFO]
    state = _load_state()
    now = dt.datetime.now()
    live_keys = {i["key"] for i in items}

    fresh = []
    for i in items:
        last = state.get(i["key"])
        hours = s["repeat_urgent_hours"] if i["severity"] == URGENT else s["repeat_attention_hours"]
        try:
            recent = last and (now - dt.datetime.fromisoformat(last)) < dt.timedelta(hours=hours)
        except ValueError:
            recent = False
        if not recent:
            fresh.append(i)

    state = {k: v for k, v in state.items() if k in live_keys}

    if not fresh:
        _save_state(state)
        print(f"{len(items)} known issue(s), nothing new to send.")
        return 0

    text = alert_text(fresh)
    print(text)
    if send and notify.send(text):
        for i in fresh:
            state[i["key"]] = now.isoformat(timespec="seconds")
    _save_state(state)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--weekly", action="store_true", help="send the weekly summary")
    p.add_argument("--check", action="store_true", help="send only new problems")
    p.add_argument("--print", action="store_true", dest="show",
                   help="print the weekly summary, send nothing")
    args = p.parse_args()

    load_dotenv(ROOT / ".env")
    config = yaml.safe_load((ROOT / "config.yaml").read_text())

    if args.check:
        return check(config)
    text = weekly_text(config)
    print(text)
    if args.weekly and not args.show:
        return 0 if notify.send(text) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
