from __future__ import annotations

import logging
import os
import re

import requests

import llm

log = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = """\
You write a short daily market digest for one reader. You are a reporter, not \
an analyst and not an advisor.

ABSOLUTE RULES:
- Describe only what HAS happened and what IS scheduled. Never state or imply \
what will happen next.
- Never recommend an action. No buy, sell, hold, enter, exit, trim, or add.
- No price targets, support levels, resistance levels, or technical signals.
- No forecasting language: no "likely to rise", "poised for", "expected to \
rally", "set to climb".
- Do not characterise anything as cheap, expensive, oversold, or overbought.
- If you do not know why something moved, say the move happened and that the \
cause is not established. Never invent a reason.
- Report only the facts given to you. Do not add figures from memory.

{mechanics_clause}

FORMAT:
- Plain text. No markdown headers, no bold, no bullet characters other than "-".
- Under {max_words} words total.
- Lead with scheduled events in the next two weeks, because those are known in \
advance and are the most useful thing here.
- Then notable moves, then filings.
- If nothing met the thresholds, say so plainly in one line. A quiet day is a \
valid and useful report.
"""

MECHANICS_ON = """\
You MAY explain transmission mechanics: how one fact mechanically relates to \
another, as a general principle. For example, "higher long-term yields reduce \
the present value of distant cash flows, which weighs more heavily on \
high-multiple companies than on value names."

This is teaching how markets work, not predicting. The test: a mechanics \
sentence must remain true regardless of what prices do tomorrow. If a sentence \
would be proven wrong by tomorrow's price action, it is a forecast and you must \
not write it."""

MECHANICS_OFF = """\
Do not explain mechanics or interpret relationships between facts. Report the \
facts alone."""


def build_fact_block(facts) -> str:
    lines = [f"AS OF: {facts.as_of.strftime('%Y-%m-%d %H:%M %Z').strip()}", ""]

    if facts.earnings:
        lines.append("SCHEDULED EARNINGS (next two weeks):")
        for item in sorted(facts.earnings, key=lambda x: x["days_away"]):
            lines.append(
                f"- {item['symbol']}: {item['date']} ({item['days_away']} days away)"
            )
        lines.append("")

    if facts.prices:
        notable = [p for p in facts.prices if p["notable"]]
        quiet = [p for p in facts.prices if not p["notable"]]

        if notable:
            lines.append("NOTABLE MOVES (exceeded threshold):")
            for p in notable:
                label = f" ({p['note']})" if p["note"] else ""
                lines.append(
                    f"- {p['symbol']}{label}: {p['last']:,.2f} "
                    f"({p['change_pct']:+.2f}% vs prior close {p['prev']:,.2f}) "
                    f"[session {p['session_date']}]"
                )
            lines.append("")

        if quiet:
            lines.append("OTHER WATCHLIST (did not exceed threshold):")
            for p in quiet:
                lines.append(f"- {p['symbol']}: {p['last']:,.2f} ({p['change_pct']:+.2f}%)")
            lines.append("")

    if facts.macro:
        lines.append("MACRO:")
        for m in facts.macro:
            flag = " [notable]" if m["notable"] else ""
            lines.append(
                f"- {m['label']}: {m['last']}{m['unit']} "
                f"({m['change']} vs prior){flag} [as of {m['observation_date']}]"
            )
        lines.append("")

    if facts.filings:
        lines.append("SEC FILINGS:")
        for f in facts.filings:
            lines.append(f"- {f['symbol']}: Form {f['form']} filed {f['filed']}")
        lines.append("")

    if facts.errors:
        lines.append("DATA GAPS (sources that failed this run):")
        for err in facts.errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


def check_guardrail(text: str, patterns: list[str]) -> list[str]:
    hits = []
    for pattern in patterns:
        try:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                hits.append(f"{pattern} -> '{match.group(0)}'")
        except re.error:
            log.warning("invalid forbidden_pattern regex: %s", pattern)
    return hits


def generate(facts, config: dict) -> dict:
    settings = config.get("digest", {})
    fact_block = build_fact_block(facts)

    provider = settings.get("provider", "anthropic").lower()

    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY", ""):
        return {
            "text": "[ANTHROPIC_API_KEY not set - raw facts below]\n\n" + fact_block,
            "fact_block": fact_block,
            "guardrail_hits": [],
            "generated": False,
        }

    system = SYSTEM_PROMPT.format(
        mechanics_clause=(
            MECHANICS_ON if settings.get("explain_mechanics", True) else MECHANICS_OFF
        ),
        max_words=settings.get("max_words", 300),
    )

    try:
        text = llm.complete(
            system=system,
            user=("Write today's digest from these facts. Report only "
                  "what is here.\n\n" + fact_block),
            config=config,
            want_json=False,
            max_tokens=1200,
        )
        if not text:
            raise ValueError("empty response")
    except Exception as exc:
        log.warning("digest generation failed", exc_info=True)
        return {
            "text": f"[digest generation failed: {exc} - raw facts below]\n\n{fact_block}",
            "fact_block": fact_block,
            "guardrail_hits": [],
            "generated": False,
        }

    hits = check_guardrail(text, config.get("forbidden_patterns", []))

    if hits:
        warning = (
            "WARNING: this digest contains language it was instructed to avoid.\n"
            "Treat the flagged parts as opinion, not fact.\n"
            + "\n".join(f"  {h}" for h in hits)
            + "\n" + "-" * 40 + "\n\n"
        )
        text = warning + text

    return {
        "text": text,
        "fact_block": fact_block,
        "guardrail_hits": hits,
        "generated": True,
    }
