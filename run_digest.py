#!/usr/bin/env python3

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

import digest as digest_module
import notify
import sources
import store

HERE = Path(__file__).parent


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def load_config(path: Path) -> dict:
    if not path.exists():
        print(f"Config not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as fh:
        return yaml.safe_load(fh)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a market digest.")
    parser.add_argument("--dry-run", action="store_true",
                        help="generate and print, but do not send")
    parser.add_argument("--facts-only", action="store_true",
                        help="print collected facts without calling the API")
    parser.add_argument("--history", action="store_true",
                        help="print recent run health and exit")
    parser.add_argument("--config", default=str(HERE.parent / "config.yaml"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("main")

    if args.history:
        store.summary()
        return 0

    load_dotenv(HERE.parent / ".env")
    config = load_config(Path(args.config))

    log.info("collecting facts...")
    facts = sources.collect(config)

    log.info(
        "collected: %d prices, %d macro, %d filings, %d earnings, %d errors",
        len(facts.prices), len(facts.macro), len(facts.filings),
        len(facts.earnings), len(facts.errors),
    )

    for err in facts.errors:
        log.warning("data gap: %s", err)

    if facts.is_empty():
        log.error("no data collected from any source - not sending")
        return 1

    if args.facts_only:
        print(digest_module.build_fact_block(facts))
        return 0

    log.info("generating digest...")
    result = digest_module.generate(facts, config)

    if result["guardrail_hits"]:
        log.warning(
            "guardrail: %d forbidden pattern(s) in output - flagged in message",
            len(result["guardrail_hits"]),
        )

    if args.dry_run:
        print("\n" + "=" * 60)
        print(result["text"])
        print("=" * 60 + "\n")
        print("(dry run - not sent, not logged)")
        return 0

    delivered = notify.send(result["text"])
    run_id = store.record(result, facts.errors, delivered)

    log.info("run %d recorded, delivered=%s", run_id, delivered)
    return 0 if delivered else 1


if __name__ == "__main__":
    sys.exit(main())
