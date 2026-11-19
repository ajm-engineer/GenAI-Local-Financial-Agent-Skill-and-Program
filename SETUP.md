# Setup

How to run AeroStock as services on an always-on Linux machine with systemd (Ubuntu or Debian). Allow about 30 minutes.

## 1. System packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git sqlite3
```

If the machine is a laptop, stop it from sleeping with the lid closed. A suspended machine is the most common reason services quietly stop overnight.

```bash
sudo sed -i 's/^#HandleLidSwitch=.*/HandleLidSwitch=ignore/' /etc/systemd/logind.conf
sudo sed -i 's/^#HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
sudo systemctl restart systemd-logind
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

## 2. Get the code

Any directory works. The installer rewrites the service files to match.

```bash
git clone https://github.com/<you>/aerostock.git ~/aerostock
cd ~/aerostock
```

## 3. Python environment and keys

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
chmod 600 .env
nano .env
```

| Key | Needed for | Where to get it |
|---|---|---|
| `SEC_USER_AGENT` | SEC filings | Your name and email, e.g. `Jane Doe jane@example.com`. SEC blocks requests without one. |
| `FRED_API_KEY` | Macro series | Free at fredaccount.stlouisfed.org |
| `ANTHROPIC_API_KEY` | Model calls when `provider: anthropic` | console.anthropic.com (usage-based) |
| `TELEGRAM_BOT_TOKEN` | Delivery | Message @BotFather and send `/newbot` |
| `TELEGRAM_CHAT_ID` | Delivery | Message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` |
| `WEBUI_TOKEN` | Web page access | Any long random string, e.g. `openssl rand -hex 24` |

Check that the model names in `config.yaml` are available on your account. A stale model name fails with a 404.

## 4. Check each piece before automating

Run these in order. Each one catches a different kind of failure.

```bash
python scripts/validate_watchlist.py          # every symbol resolves
python scripts/run_digest.py --facts-only     # data sources reachable, no model call
python scripts/run_digest.py --dry-run        # first model call, printed, not sent
python scripts/run_digest.py                  # sends to Telegram
python scripts/texas_tracker.py --status      # no keys or network needed
python scripts/research_loop.py --once -v     # one cycle, nothing recorded
python scripts/ledger.py --score              # empty ledger, but it opens
```

A symbol that doesn't resolve gives an empty section instead of an error, so fix the watchlist before you rely on any report.

## 5. Optional: run models locally

Set `provider: ollama` under `digest`, `desk` or `panel` in `config.yaml`. The panel uses Ollama by default.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:9b
ollama run qwen3.5:9b "reply with the single word: ok"
```

On a machine with an NVIDIA GPU, check `nvidia-smi` while a model runs to confirm it is using the GPU and not falling back to the CPU.

## 6. Install the services

Run as your normal user. The script asks for sudo.

```bash
sh install/install_services.sh
```

It installs and starts:

| Unit | What it does |
|---|---|
| `market-digest-web.service` | The web page on port 8000 |
| `research-loop.service` | The research loop, once an hour |
| `market-digest.timer` | Digest on weekdays at 07:30 |
| `nightly-report.timer` | Condenses overnight research at 06:30 |
| `box-health-check.timer` | Health check every 10 minutes, alerts only on problems |
| `box-health-weekly.timer` | Weekly health summary on Sunday evening |
| `audit-export.timer` | Monthly export of the ledger, which is also its backup |

The web service listens on all interfaces, so it won't start unless `WEBUI_TOKEN` is set in `.env`. Open `http://<machine-ip>:8000/?token=<your token>` from a device on your network.

`box-health-check` watches the services listed under `health.services` in `config.yaml`. Remove any you don't run (for example `ollama` or `tailscaled`).

## 7. Reaching it away from home

Don't port-forward port 8000. Install a VPN such as Tailscale on the machine and on your phone, then use the machine's VPN address:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

In a phone browser, "Add to Home Screen" makes the page open like an app.

## 8. Routine

- **Daily:** read the digest.
- **Weekly:** grade the calls that came due (the Grade tab, or `python scripts/ledger.py --due`). Grading is the step that makes the whole thing work. Ungraded calls teach it nothing.
- **Monthly:** check `python scripts/ledger.py --score`, and keep a copy of the export from `data/exports/` somewhere off the machine.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Services stop overnight | Machine suspended | Step 1 |
| 404 from the API | Model name not available | Step 3 |
| SEC filings always empty | Missing or generic `SEC_USER_AGENT` | Use a real name and email |
| Telegram silent | Wrong token or chat ID | `python scripts/run_digest.py --dry-run` to isolate it |
| Web service keeps restarting | `WEBUI_TOKEN` missing from `.env` | Set it, then `sudo systemctl restart market-digest-web` |
| Many rejected claims in the log | The model is hedging | Normal at first. Check `research_loop.py --report` |

```bash
journalctl -u research-loop -n 100 --no-pager
journalctl -u market-digest -n 50 --no-pager
journalctl -u market-digest-web -n 50 --no-pager
```

The ledger (`data/ledger.db`) is the only thing here that can't be regenerated. Back it up:

```bash
sqlite3 data/ledger.db ".backup $HOME/ledger-backup.db"
```
