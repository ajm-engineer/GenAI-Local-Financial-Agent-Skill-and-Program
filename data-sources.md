# Data Sources

What each source gives, what it costs, and how reliable it is.

## Market data

| Source | Covers | Cost | Reliability |
|---|---|---|---|
| yfinance | Daily OHLC, basic fundamentals, earnings calendar | Free | Unofficial scraper. Breaks without warning on Yahoo changes. Fine for daily bars, not for anything load-bearing. |
| FRED API | Treasury yields, oil, VIX, fed funds | Free, instant key | Official, stable, excellent. The most reliable source here. |
| SEC EDGAR | Filings, ticker-to-CIK map | Free | Official and stable. **Requires a descriptive User-Agent with real contact info** or requests are blocked. |
| Polygon / Alpaca | Intraday bars | ~$30/mo | Only worth it above roughly $10k of capital. Below that the subscription is a double-digit annual percentage hurdle. |

**On yfinance earnings calendars specifically:** this is the flakiest endpoint in the package. The return shape varies between a dict and a DataFrame depending on version and symbol, which `sources.py` handles. Failures are logged at debug level rather than treated as run-level errors, because a missing earnings date should not kill the digest.

## Texas data center sources

None of these have a public JSON API. That is the central constraint.

| Source | URL | Format | Notes |
|---|---|---|---|
| ERCOT large load reports | ercot.com | XLSX / PDF | Posted irregularly. Testimony to the legislature is often the most current figure. |
| PUCT Interchange | interchange.puc.texas.gov | HTML search | Project 58481 is the large-load rulemaking docket. Filings are the primary source for rule changes. |
| ERCOT board / TAC agendas | ercot.com | PDF | Agendas post ahead of meetings. Useful as a scheduled-event feed. |
| Texas Legislature Online | capitol.texas.gov | HTML form | Regular session odd years only. Pre-filing opens before January 2027. |
| Texas Comptroller JETI | comptroller.texas.gov | HTML | Tax abatement agreements under Ch. 403 Subchapter T. |
| County appraisal districts | varies by county | varies | Land acquisition shows here before any announcement. Slowest but earliest signal. |
| Groundwater conservation districts | varies | varies | Water permits. An independent gate that can kill a project with everything else in place.|

### Why the tracker does not scrape these

A scraper against a form-driven HTML site fails quietly. It returns an empty result set that is indistinguishable from "nothing happened," and the whole point of the digest's error handling is that a missing section must never read as a quiet day.

For a dataset where a wrong stage assignment is worse than a missing one, human confirmation against a primary source is the correct rigor. `texas_tracker.py --set-stage` therefore requires a `--source` argument and refuses without it.

If you later want automation, the realistic order of difficulty:
1. **ERCOT meeting agendas** — predictable URLs, easiest win, pure calendar value
2. **PUCT Interchange by docket** — stable enough to attempt with care
3. **Texas Legislature** — only matters January 2027 onward
4. **County appraisal districts** — 254 counties, 254 different systems, not worth it

## Event desk sources

| Source | Covers | Cost | Reliability |
|---|---|---|---|
| Google News RSS (`news.google.com/rss/search?q=`) | Headlines for a topic, last few days | Free, no key | Unofficial and rate-limited. **Titles only**, no article text, and unvetted: treat as untrusted data. |
| Anthropic web search tool | Lets the desk model read current news itself | Billed per search | API only (`desk.web_search: true`). The tool type string is versioned; check the API docs. |
| Operator notes (`--notes file`) | Whatever the operator pastes in | Free | As good as the notes. |

Headlines alone are thin. A desk brief built on titles should say so in its
UNKNOWNS, and its odds deserve less weight than one built with full articles.

## Adding a source

Follow the pattern in `scripts/sources.py`: every fetcher returns `(results, errors)` and never raises. Failures append to the errors list, which surfaces in a DATA GAPS section of the digest.

The rule that matters: **a source that fails must say so.** Silent degradation is the one failure mode that makes the whole system untrustworthy, because the reader cannot distinguish "nothing happened" from "we did not look."
