from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
import zlib

import ledger

MAX_BYTES = 400_000


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def prompt_fingerprint(prompt: str) -> str:
    return _hash(prompt)[:12]


def put(text: str) -> str:
    text = (text or "")[:MAX_BYTES]
    h = _hash(text)
    c = ledger.conn()
    try:
        c.execute("INSERT OR IGNORE INTO snapshots (hash, created_at, size, body) "
                  "VALUES (?,?,?,?)",
                  (h, dt.datetime.now().isoformat(timespec="seconds"),
                   len(text), zlib.compress(text.encode("utf-8", errors="replace"), 9)))
        c.commit()
    finally:
        c.close()
    return h


def get(h: str) -> str | None:
    c = ledger.conn()
    try:
        row = c.execute("SELECT body FROM snapshots WHERE hash=?", (h,)).fetchone()
    finally:
        c.close()
    return zlib.decompress(row["body"]).decode("utf-8", errors="replace") if row else None


def attach(claim_id: str, origin: str, inputs: str = "", model: str = "",
           provider: str = "", prompt: str = "", sources: str = "") -> bool:
    try:
        h = put(inputs) if inputs else ""
        c = ledger.conn()
        try:
            c.execute(
                "INSERT INTO claim_inputs (claim_id, origin, snapshot_hash, model, "
                "provider, prompt_hash, sources, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (claim_id, origin, h, model, provider,
                 prompt_fingerprint(prompt) if prompt else "", sources,
                 dt.datetime.now().isoformat(timespec="seconds")))
            c.commit()
        finally:
            c.close()
        return True
    except sqlite3.Error as exc:
        print(f"warning: snapshot not recorded for {claim_id}: {exc}")
        return False


def model_name(settings: dict) -> tuple[str, str]:
    prov = (settings.get("provider") or "").lower()
    model = settings.get("local_model") if prov == "ollama" else settings.get("model")
    return str(model or ""), prov
