from __future__ import annotations

import datetime as dt
import logging
import os
from dataclasses import dataclass, field

import requests
import yfinance as yf

log = logging.getLogger(__name__)

SEC_UA = os.environ.get("SEC_USER_AGENT", "")

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
SEC_TICKER_MAP = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

RATE_SERIES = {"DGS10", "DGS2", "DGS30", "DFF", "DFEDTARU", "FEDFUNDS"}


@dataclass
class Facts:
    as_of: dt.datetime
    prices: list[dict] = field(default_factory=list)
    macro: list[dict] = field(default_factory=list)
    filings: list[dict] = field(default_factory=list)
    earnings: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.prices or self.macro or self.filings or self.earnings)


def fetch_prices(watchlist: list[dict], thresholds: dict) -> tuple[list[dict], list[str]]:
    results, errors = [], []

    equity_threshold = float(thresholds.get("price_move_pct", 2.0))
    crypto_threshold = float(thresholds.get("crypto_move_pct", 4.0))

    for entry in watchlist:
        symbol = entry["symbol"]
        asset_type = entry.get("asset_type", "equity")

        try:
            hist = yf.Ticker(symbol).history(period="7d")

            if hist.empty or len(hist) < 2:
                errors.append(f"{symbol}: insufficient price history")
                continue

            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            change_pct = ((last - prev) / prev) * 100.0 if prev else 0.0

            threshold = crypto_threshold if asset_type == "crypto" else equity_threshold

            results.append({
                "symbol": symbol,
                "asset_type": asset_type,
                "note": entry.get("note", ""),
                "last": round(last, 4),
                "prev": round(prev, 4),
                "change_pct": round(change_pct, 2),
                "notable": abs(change_pct) >= threshold,
                "session_date": hist.index[-1].strftime("%Y-%m-%d"),
            })

        except Exception as exc:
            errors.append(f"{symbol}: price fetch failed ({exc})")
            log.warning("price fetch failed for %s", symbol, exc_info=True)

    return results, errors


def fetch_macro(series_config: list[dict], thresholds: dict) -> tuple[list[dict], list[str]]:
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        return [], ["FRED_API_KEY not set - macro section skipped"]

    results, errors = [], []
    move_bps = float(thresholds.get("macro_move_bps", 5))
    move_pct = float(thresholds.get("macro_move_pct", 2.0))

    start = (dt.date.today() - dt.timedelta(days=14)).isoformat()

    for series in series_config:
        series_id = series["series_id"]
        try:
            resp = requests.get(
                FRED_BASE,
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": start,
                    "sort_order": "desc",
                    "limit": 10,
                },
                timeout=20,
            )
            resp.raise_for_status()
            observations = resp.json().get("observations", [])

            valid = [o for o in observations if o.get("value") not in (".", "", None)]

            if len(valid) < 2:
                errors.append(f"{series_id}: not enough observations")
                continue

            last = float(valid[0]["value"])
            prev = float(valid[1]["value"])
            delta = last - prev

            is_rate = series_id in RATE_SERIES
            if is_rate:
                change_desc = f"{delta * 100:+.0f} bps"
                notable = abs(delta * 100) >= move_bps
            else:
                pct = (delta / prev * 100.0) if prev else 0.0
                change_desc = f"{pct:+.2f}%"
                notable = abs(pct) >= move_pct

            results.append({
                "series_id": series_id,
                "label": series["label"],
                "unit": series.get("unit", ""),
                "last": last,
                "prev": prev,
                "change": change_desc,
                "notable": notable,
                "observation_date": valid[0]["date"],
            })

        except Exception as exc:
            errors.append(f"{series_id}: FRED fetch failed ({exc})")
            log.warning("FRED fetch failed for %s", series_id, exc_info=True)

    return results, errors


_cik_cache: dict[str, int] | None = None


def _load_cik_map() -> dict[str, int]:
    global _cik_cache
    if _cik_cache is not None:
        return _cik_cache

    if not SEC_UA:
        raise RuntimeError("SEC_USER_AGENT not set")

    resp = requests.get(SEC_TICKER_MAP, headers={"User-Agent": SEC_UA}, timeout=20)
    resp.raise_for_status()

    _cik_cache = {
        entry["ticker"].upper(): int(entry["cik_str"])
        for entry in resp.json().values()
    }
    return _cik_cache


def fetch_filings(
    watchlist: list[dict], forms: list[str], lookback_days: int
) -> tuple[list[dict], list[str]]:
    if not SEC_UA:
        return [], ["SEC_USER_AGENT not set - filings section skipped"]

    results, errors = [], []
    cutoff = dt.date.today() - dt.timedelta(days=lookback_days)
    wanted = {f.upper() for f in forms}

    try:
        cik_map = _load_cik_map()
    except Exception as exc:
        return [], [f"SEC ticker map unavailable ({exc})"]

    for entry in watchlist:
        if entry.get("asset_type", "equity") != "equity":
            continue

        symbol = entry["symbol"].upper()
        cik = cik_map.get(symbol)

        if cik is None:
            errors.append(f"{symbol}: no CIK found (not an SEC filer?)")
            continue

        try:
            resp = requests.get(
                SEC_SUBMISSIONS.format(cik=cik),
                headers={"User-Agent": SEC_UA},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            recent = data.get("filings", {}).get("recent", {})
            form_list = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            docs = recent.get("primaryDocument", [])

            for i, form in enumerate(form_list):
                if form.upper() not in wanted:
                    continue

                try:
                    filed = dt.date.fromisoformat(dates[i])
                except (ValueError, IndexError):
                    continue

                if filed < cutoff:
                    break

                accession = accessions[i].replace("-", "") if i < len(accessions) else ""
                document = docs[i] if i < len(docs) else ""
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{accession}/{document}"
                ) if accession and document else ""

                results.append({
                    "symbol": symbol,
                    "form": form,
                    "filed": dates[i],
                    "url": url,
                })

        except Exception as exc:
            errors.append(f"{symbol}: SEC fetch failed ({exc})")
            log.warning("SEC fetch failed for %s", symbol, exc_info=True)

    return results, errors


def fetch_earnings(watchlist: list[dict], horizon_days: int) -> tuple[list[dict], list[str]]:
    results, errors = [], []
    today = dt.date.today()
    cutoff = today + dt.timedelta(days=horizon_days)

    for entry in watchlist:
        if entry.get("asset_type", "equity") not in ("equity", "foreign"):
            continue

        symbol = entry["symbol"]
        try:
            calendar = yf.Ticker(symbol).calendar

            dates = None
            if isinstance(calendar, dict):
                dates = calendar.get("Earnings Date")
            elif calendar is not None and hasattr(calendar, "empty"):
                if not calendar.empty and "Earnings Date" in calendar.index:
                    dates = calendar.loc["Earnings Date"].tolist()

            if not dates:
                continue

            if not isinstance(dates, list):
                dates = [dates]

            for raw in dates:
                date = raw.date() if hasattr(raw, "date") else raw
                if not isinstance(date, dt.date):
                    continue
                if today <= date <= cutoff:
                    results.append({
                        "symbol": symbol,
                        "date": date.isoformat(),
                        "days_away": (date - today).days,
                    })
                    break

        except Exception as exc:
            log.debug("earnings fetch failed for %s: %s", symbol, exc)

    return results, errors


def collect(config: dict) -> Facts:
    facts = Facts(as_of=dt.datetime.now())

    watchlist = config.get("watchlist", [])
    thresholds = config.get("thresholds", {})

    facts.prices, errs = fetch_prices(watchlist, thresholds)
    facts.errors.extend(errs)

    facts.macro, errs = fetch_macro(config.get("macro", []), thresholds)
    facts.errors.extend(errs)

    facts.filings, errs = fetch_filings(
        watchlist,
        config.get("filing_forms", ["8-K"]),
        int(thresholds.get("filing_lookback_days", 2)),
    )
    facts.errors.extend(errs)

    facts.earnings, errs = fetch_earnings(
        watchlist, int(thresholds.get("earnings_horizon_days", 14))
    )
    facts.errors.extend(errs)

    return facts
