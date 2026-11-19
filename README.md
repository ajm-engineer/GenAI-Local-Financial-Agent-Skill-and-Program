# AeroStock

A self-hosted market research box. It writes a plain-language market digest every weekday morning, runs a research loop that turns changes in public sources into dated, checkable claims, and runs an event desk that gives scenario odds on request. Every call it makes goes into a ledger and gets graded, so you can see whether its odds are worth anything.

It runs on a small always-on Linux machine (an old laptop or mini PC is plenty), sends reports to Telegram, and serves a phone-friendly web page for grading calls and running briefs.

| Grade | Desk |
|---|---|
| ![Grading calls](docs/screenshots/grade.png) | ![Event desk](docs/screenshots/desk.png) |
| **Score** | **Texas** |
| ![Calibration score](docs/screenshots/score.png) | ![Texas tracker](docs/screenshots/texas.png) |

*Screenshots use made-up sample data from `preview/build_preview.py`.*

## What it does

- **Daily digest.** Prices, Treasury yields and other macro series (FRED), SEC filings (EDGAR) and upcoming earnings for a watchlist, summarized in a few hundred words. A regex guardrail blocks buy/sell and price-direction language, so the digest describes and never advises.
- **Research loop.** Polls public sources on a schedule, detects real changes, and has a model write falsifiable claims ("X happens on or before date Y") with a confidence. Vague claims are rejected before they reach the ledger.
- **Event desk.** On request, writes a brief on one topic: scenarios with odds, what the price already reflects, setups ranked by how sound the logic is, traps, unknowns, and 2 to 5 claims for grading. It never sizes a position.
- **Ledger and scoring.** SQLite ledger with Brier scores per track and category, compared against a coin flip, with minimum-sample warnings so a lucky streak isn't mistaken for skill.
- **Forecaster panel.** Several forecasters (base rate, outside view, inside view, skeptic and others) each give a probability. Their weights follow their track records, so the blend improves only as fast as the evidence allows.
- **Texas data center tracker.** ERCOT large-load pipeline, PUCT rulemakings, bills and a regulatory calendar.
- **AI silicon tracker.** Claims about the CUDA moat, adoption of non-Nvidia accelerators, and pricing.
- **Web UI.** FastAPI and a single HTML page. Grade calls with two taps, run or import desk briefs, check the score, read digests, and watch the machine's health.
- **Box health.** CPU temperature, disk, memory, services and loop activity, with alerts to Telegram when something breaks and a weekly summary.
- **Agent skill.** `SKILL.md` and `references/` make the whole thing usable as a Claude skill, so an assistant can run the tools and follow the same rules.

## Layout

```
SKILL.md              rules for an AI assistant running the system
config.yaml           watchlist, macro series, thresholds, model choices, guardrails
scripts/              the programs (digest, research loop, desk, ledger, panel, web UI ...)
scripts/static/       the web page and its icons
references/           background notes the desk and the loop read
install/              systemd services and timers, plus an installer
preview/              builds offline preview pages from sample data
docs/SETUP.md         full install on a Linux box
```

## Quick start

Python 3.10 or newer.

```bash
git clone https://github.com/<you>/aerostock.git
cd aerostock
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python scripts/texas_tracker.py --status       # works with no keys and no network
python scripts/run_digest.py --facts-only      # fetches market data, no model call
python preview/build_preview.py                # sample-data pages in preview/
python scripts/webui.py                        # http://127.0.0.1:8000
```

To install it as a set of services on an always-on machine, follow [docs/SETUP.md](docs/SETUP.md).

## Configuration

**Keys** go in `.env` (see `.env.example`). All are optional; anything missing is reported as a data gap instead of crashing.

| Variable | Used for |
|---|---|
| `ANTHROPIC_API_KEY` | Digest, research loop and desk when the provider is `anthropic` |
| `FRED_API_KEY` | Yields, oil, VIX and other macro series (free key) |
| `SEC_USER_AGENT` | EDGAR filings. SEC requires a real name and email |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Delivery of digests, briefs and alerts |
| `WEBUI_TOKEN` | Access token for the web page (see Security) |

**Settings** are in `config.yaml`: the watchlist, macro series, move thresholds, which model each part uses, and the guardrail patterns. Each part can use the Anthropic API or a local model through [Ollama](https://ollama.com) (`provider: ollama`). The panel uses Ollama by default. Run `python scripts/validate_watchlist.py` after editing the watchlist.

To put your own logo in the page header, drop `logo.png` (or `.svg`, `.jpg`) into `scripts/static/`.

## Security

- The web page has no user accounts. It listens on `127.0.0.1` by default and refuses to listen on any other address unless `WEBUI_TOKEN` is set (or you pass `--allow-no-token`).
- The token travels as `?token=...` in the URL, so it can end up in browser history and logs. Treat it as a second layer, not real authentication.
- Never port-forward the web page to the internet. For access away from home, use a VPN such as Tailscale or WireGuard.
- `.env` holds your API keys. Keep it at `chmod 600` and never commit it (it is in `.gitignore`).
- Headlines and web pages are untrusted input to a language model. The prompts tell the model to treat them as data, but prompt injection is not a solved problem. Read what the desk produces before acting on any of it.

## Limitations

- A system reading public sources on a schedule has no information edge; by the time news reaches a feed, it is usually in the price. The ledger exists to measure this honestly. Expect scores near a coin flip, and don't trust any score until at least 30 calls have resolved.
- The notes in `references/` reflect public reporting as of November 2026 and go stale. Check anything time-sensitive against a current source.
- Free data sources change without notice. `yfinance` is an unofficial library and can break when Yahoo changes its site.
- The worked examples in the docs use a fictional company. They show the format, not real events.

## Disclaimer

This project is for research and education. It is not financial, investment, legal or tax advice, and nothing it produces is a recommendation to buy, sell or hold any security. Model output can be wrong, stale or made up. Markets carry risk, including the loss of everything you invest. Do your own research and talk to a licensed professional before making financial decisions.

This software is provided "as is", without warranty of any kind. The author is not responsible for any financial loss, trading decision, damage or misuse resulting from its use. You are responsible for following the terms of every data source and service you connect to it (including SEC EDGAR's fair-access rules, FRED, Yahoo Finance, Anthropic and Telegram) and for complying with all applicable laws, including securities laws. Don't use it to trade on material non-public information, manipulate markets, or scrape services against their terms.

This project is not affiliated with or endorsed by any company, agency or data provider it mentions. Company names and tickers appear only to describe public information, and trademarks belong to their owners.

## License

MIT. See [LICENSE](LICENSE).
