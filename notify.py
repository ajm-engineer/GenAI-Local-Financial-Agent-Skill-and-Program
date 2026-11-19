from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4000


TELEGRAM_DOC = "https://api.telegram.org/bot{token}/sendDocument"
MAX_DOC_BYTES = 45 * 1024 * 1024


def send_file(path, caption: str = "") -> bool:
    from pathlib import Path
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    path = Path(path)
    if not token or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; not sending %s", path.name)
        return False
    if not path.exists():
        log.error("file to send does not exist: %s", path)
        return False
    if path.stat().st_size > MAX_DOC_BYTES:
        log.error("%s is %.1f MB, over Telegram's limit; copy it off the box by hand",
                  path.name, path.stat().st_size / 1e6)
        send(f"Audit bundle {path.name} is too large to send through Telegram. "
             f"Copy it off the box: scp user@your-server:{path} .")
        return False
    try:
        with open(path, "rb") as fh:
            resp = requests.post(
                TELEGRAM_DOC.format(token=token),
                data={"chat_id": chat_id, "caption": caption[:1000]},
                files={"document": (path.name, fh, "application/zip")},
                timeout=120)
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.error("Telegram file send failed: %s", exc)
        return False


def _chunk(text: str, size: int = MAX_LEN) -> list[str]:
    if len(text) <= size:
        return [text]

    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > size:
            if current:
                chunks.append(current)
            while len(line) > size:
                chunks.append(line[:size])
                line = line[size:]
            current = line
        else:
            current = f"{current}\n{line}" if current else line

    if current:
        chunks.append(current)
    return chunks


def send(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        log.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        print("\n--- digest (Telegram not configured) ---\n")
        print(text)
        return False

    chunks = _chunk(text)
    ok = True

    for i, chunk in enumerate(chunks, 1):
        body = chunk
        if len(chunks) > 1:
            body = f"[{i}/{len(chunks)}]\n{chunk}"

        try:
            resp = requests.post(
                TELEGRAM_API.format(token=token),
                json={"chat_id": chat_id, "text": body},
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as exc:
            log.error("Telegram send failed for chunk %d: %s", i, exc)
            ok = False

    return ok
