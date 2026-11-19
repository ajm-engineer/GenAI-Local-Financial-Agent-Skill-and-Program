#!/usr/bin/env python3

import sys

from pathlib import Path
import yaml
import yfinance as yf

QUOTE_TYPE_TO_ASSET = {
    "EQUITY": "equity",
    "ETF": "equity",
    "MUTUALFUND": "fund",
    "CRYPTOCURRENCY": "crypto",
    "INDEX": "equity",
}


def load_config(path="config.yaml"):
    with open(path) as fh:
        return yaml.safe_load(fh)


def probe(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
    except Exception as exc:
        return False, {"error": str(exc)}

    name = info.get("longName") or info.get("shortName")
    quote_type = info.get("quoteType")

    if not name and not quote_type:
        return False, {"error": "no data returned - symbol likely does not exist"}

    try:
        hist = ticker.history(period="5d")
        has_prices = not hist.empty
        last_close = float(hist["Close"].iloc[-1]) if has_prices else None
    except Exception as exc:
        has_prices = False
        last_close = None
        info["_history_error"] = str(exc)

    return True, {
        "name": name,
        "quote_type": quote_type,
        "exchange": info.get("fullExchangeName") or info.get("exchange"),
        "currency": info.get("currency"),
        "has_prices": has_prices,
        "last_close": last_close,
    }


def main():
    config = load_config()
    entries = config.get("watchlist", [])

    if not entries:
        print("No watchlist entries in config.yaml.")
        return 1

    print(f"Checking {len(entries)} symbols...\n")

    problems = []

    for entry in entries:
        symbol = entry["symbol"]
        declared = entry.get("asset_type", "equity")

        ok, details = probe(symbol)

        if not ok:
            print(f"  FAIL  {symbol:10s}  {details['error']}")
            problems.append(symbol)
            continue

        name = details["name"] or "(unnamed)"
        quote_type = details["quote_type"] or "?"
        exchange = details["exchange"] or "?"
        currency = details["currency"] or "?"

        line = f"  OK    {symbol:10s}  {name}"
        print(line)
        print(f"        {'':10s}  type={quote_type}  exchange={exchange}  currency={currency}")

        if details["last_close"] is not None:
            print(f"        {'':10s}  last close: {details['last_close']:,.2f} {currency}")
        else:
            print(f"        {'':10s}  WARNING: no price history returned")
            problems.append(symbol)

        expected = QUOTE_TYPE_TO_ASSET.get(quote_type)
        if expected and declared not in (expected, "foreign"):
            print(
                f"        {'':10s}  MISMATCH: config says asset_type '{declared}', "
                f"provider says this is a {quote_type} (expected '{expected}')"
            )
            problems.append(symbol)

        if currency not in ("USD", "?") and declared != "foreign":
            print(
                f"        {'':10s}  NOTE: trades in {currency}, so its session does "
                f"not align with US market hours. Consider asset_type: foreign"
            )

        print()

    print("-" * 70)
    if problems:
        unique = sorted(set(problems))
        print(f"\n{len(unique)} symbol(s) need attention: {', '.join(unique)}")
        print("\nFix these in config.yaml before relying on the digest. A symbol")
        print("that does not resolve produces a silently empty section, not an error.")
        return 1

    print("\nAll symbols resolved cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
