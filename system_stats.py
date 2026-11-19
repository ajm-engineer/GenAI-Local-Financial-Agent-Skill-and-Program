from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

POWER = Path("/sys/class/power_supply")
THERMAL = Path("/sys/class/thermal")
NET = Path("/sys/class/net")


def _read(path: Path, default=None):
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return default


def _int(path: Path, default=None):
    v = _read(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _run(cmd: list[str], timeout: int = 5) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def power() -> dict:
    out = {"has_battery": False, "on_ac": None, "percent": None,
           "status": None, "health_pct": None, "minutes_left": None}

    if not POWER.exists():
        return out

    for entry in sorted(POWER.iterdir()):
        kind = _read(entry / "type", "")

        if kind == "Mains":
            online = _int(entry / "online")
            if online is not None:
                out["on_ac"] = bool(online)

        elif kind == "Battery":
            out["has_battery"] = True
            out["percent"] = _int(entry / "capacity")
            out["status"] = _read(entry / "status")

            full = _int(entry / "charge_full") or _int(entry / "energy_full")
            design = (_int(entry / "charge_full_design")
                      or _int(entry / "energy_full_design"))
            if full and design:
                out["health_pct"] = round(full / design * 100)

            now = _int(entry / "charge_now") or _int(entry / "energy_now")
            rate = _int(entry / "current_now") or _int(entry / "power_now")
            if out["status"] == "Discharging" and now and rate:
                out["minutes_left"] = round(now / rate * 60)

    return out


def thermals() -> dict:
    out = {"cpu_c": None, "zones": []}
    if not THERMAL.exists():
        return out

    best = None
    for zone in sorted(THERMAL.glob("thermal_zone*")):
        raw = _int(zone / "temp")
        if raw is None:
            continue
        celsius = round(raw / 1000, 1)
        ztype = _read(zone / "type", zone.name)
        out["zones"].append({"name": ztype, "c": celsius})
        if ztype == "x86_pkg_temp" or best is None or celsius > best:
            if ztype == "x86_pkg_temp":
                out["cpu_c"] = celsius
            best = max(best or 0, celsius)

    if out["cpu_c"] is None:
        out["cpu_c"] = best
    return out


def _wifi_detail(iface: str) -> dict:
    out = {}
    txt = _run(["iw", "dev", iface, "link"])
    if not txt or "Not connected" in txt:
        return out

    m = re.search(r"SSID:\s*(.+)", txt)
    if m:
        out["ssid"] = m.group(1).strip()
    m = re.search(r"signal:\s*(-?\d+)\s*dBm", txt)
    if m:
        dbm = int(m.group(1))
        out["signal_dbm"] = dbm
        out["signal_quality"] = ("excellent" if dbm >= -50 else
                                 "good" if dbm >= -60 else
                                 "fair" if dbm >= -70 else "poor")
    m = re.search(r"rx bitrate:\s*([\d.]+)\s*MBit/s", txt)
    if m:
        out["rx_mbps"] = float(m.group(1))
    return out


def network() -> dict:
    out = {"interfaces": [], "default_route": None, "tailscale": None}

    routes = _run(["ip", "-j", "route", "show", "default"])
    if routes:
        try:
            parsed = json.loads(routes)
            if parsed:
                out["default_route"] = {
                    "dev": parsed[0].get("dev"),
                    "gateway": parsed[0].get("gateway"),
                    "metric": parsed[0].get("metric"),
                }
        except json.JSONDecodeError:
            pass

    addrs = _run(["ip", "-j", "addr"])
    try:
        parsed = json.loads(addrs) if addrs else []
    except json.JSONDecodeError:
        parsed = []

    for link in parsed:
        name = link.get("ifname", "")
        if name == "lo":
            continue

        ipv4 = [a["local"] for a in link.get("addr_info", [])
                if a.get("family") == "inet"]

        iface = {
            "name": name,
            "state": link.get("operstate", "UNKNOWN"),
            "mac": link.get("address"),
            "ipv4": ipv4,
            "is_default": (out["default_route"] or {}).get("dev") == name,
            "kind": ("wifi" if name.startswith(("wl", "wlan")) else
                     "tailscale" if name.startswith("tailscale") else
                     "ethernet" if name.startswith(("en", "eth")) else "other"),
        }

        if iface["kind"] == "wifi" and iface["state"] == "UP":
            iface.update(_wifi_detail(name))

        speed = _int(NET / name / "speed")
        if speed and speed > 0:
            iface["speed_mbps"] = speed

        out["interfaces"].append(iface)

    ts = _run(["tailscale", "status", "--json"], timeout=8)
    if ts:
        try:
            data = json.loads(ts)
            out["tailscale"] = {
                "state": data.get("BackendState"),
                "name": (data.get("Self") or {}).get("DNSName", "").rstrip("."),
                "ips": (data.get("Self") or {}).get("TailscaleIPs", []),
                "online": (data.get("Self") or {}).get("Online"),
                "peers": len(data.get("Peer") or {}),
            }
        except (json.JSONDecodeError, AttributeError):
            pass

    return out


def gpu() -> dict:
    out = {"available": False}
    txt = _run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,"
                "memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits"])
    if not txt:
        return out

    parts = [p.strip() for p in txt.strip().split(",")]
    if len(parts) < 5:
        return out

    def num(v):
        try:
            return float(v)
        except ValueError:
            return None

    used, total = num(parts[3]), num(parts[4])
    out.update({
        "available": True,
        "name": parts[0],
        "temp_c": num(parts[1]),
        "util_pct": num(parts[2]),
        "memory_used_mb": used,
        "memory_total_mb": total,
        "memory_pct": round(used / total * 100) if used and total else None,
        "power_w": num(parts[5]) if len(parts) > 5 else None,
        "model_loaded": bool(used and used > 1000),
    })
    return out


def host() -> dict:
    out = {}

    up = _read(Path("/proc/uptime"))
    if up:
        try:
            secs = float(up.split()[0])
            d, rem = divmod(int(secs), 86400)
            h, rem = divmod(rem, 3600)
            out["uptime"] = f"{d}d {h}h {rem // 60}m" if d else f"{h}h {rem // 60}m"
            out["uptime_seconds"] = int(secs)
        except (ValueError, IndexError):
            pass

    try:
        l1, l5, l15 = os.getloadavg()
        out["load"] = [round(l1, 2), round(l5, 2), round(l15, 2)]
        out["cpus"] = os.cpu_count()
    except OSError:
        pass

    mem = _read(Path("/proc/meminfo"))
    if mem:
        vals = {}
        for line in mem.splitlines():
            m = re.match(r"(\w+):\s+(\d+)", line)
            if m:
                vals[m.group(1)] = int(m.group(2))
        total, avail = vals.get("MemTotal"), vals.get("MemAvailable")
        if total and avail:
            out["mem_total_mb"] = round(total / 1024)
            out["mem_used_mb"] = round((total - avail) / 1024)
            out["mem_pct"] = round((total - avail) / total * 100)

    try:
        du = shutil.disk_usage("/")
        out["disk_total_gb"] = round(du.total / 1e9, 1)
        out["disk_used_gb"] = round(du.used / 1e9, 1)
        out["disk_pct"] = round(du.used / du.total * 100)
    except OSError:
        pass

    return out


def services() -> dict:
    out = {}
    for name in ("ollama", "research-loop", "market-digest-web", "ssh", "tailscaled"):
        txt = _run(["systemctl", "is-active", name])
        out[name] = (txt or "").strip() or "unknown"
    return out


def all_stats() -> dict:
    return {
        "power": power(),
        "thermals": thermals(),
        "network": network(),
        "gpu": gpu(),
        "host": host(),
        "services": services(),
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


if __name__ == "__main__":
    print(json.dumps(all_stats(), indent=2))
