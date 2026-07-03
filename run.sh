#!/bin/bash
# Runs one bot cycle. Called hourly by launchd (see launchd/*.plist),
# also fine to run by hand. Secrets live in .env (gitignored), NOT here.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p logs

# Use the project venv if present, otherwise system python3
if [ -x ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
else
    PYTHON="python3"
fi

# bot_8b.py loads .env itself
"$PYTHON" bot_8b.py >> logs/bot.log 2>&1

# Publish the paper equity to GitHub Pages (docs/) when it changed, then
# sync with the remote every cycle (self-heals a previously failed push).
# Failures here must not affect the bot run — log and move on.
{
    if [ -f state/paper_equity.csv ] && ! cmp -s state/paper_equity.csv docs/paper_equity.csv; then
        cp state/paper_equity.csv docs/paper_equity.csv
        cp state/paper_state.json docs/status.json
        # 4h curiosity track rides along on the daily publish, if it exists
        [ -f state/paper_equity_4h.csv ] && cp state/paper_equity_4h.csv docs/paper_equity_4h.csv
        git add docs/
        git commit -q -m "paper: equity through $(tail -1 state/paper_equity.csv | cut -d, -f1)"
    fi
    git pull --rebase -q && git push -q
} >> logs/bot.log 2>&1 || echo "[publish] git sync failed (will retry next cycle)" >> logs/bot.log
