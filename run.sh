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
    # Publish whenever EITHER track's CSV changed (the 4h one updates every
    # 4 hours; previously it only rode along on the once-a-day daily publish,
    # so the dashboard lagged it by up to 24h).
    changed=0
    for f in paper_equity.csv paper_equity_4h.csv; do
        if [ -f "state/$f" ] && ! cmp -s "state/$f" "docs/$f"; then
            cp "state/$f" "docs/$f"
            changed=1
        fi
    done
    if [ "$changed" = 1 ]; then
        [ -f state/paper_state.json ] && cp state/paper_state.json docs/status.json
        msg="paper: equity update"
        [ -f state/paper_equity.csv ] && msg="paper: equity through $(tail -1 state/paper_equity.csv | cut -d, -f1)"
        [ -f state/paper_equity_4h.csv ] && msg="$msg, 4h $(tail -1 state/paper_equity_4h.csv | cut -d, -f1)"
        git add docs/
        git commit -q -m "$msg"
    fi
    git pull --rebase -q && git push -q
} >> logs/bot.log 2>&1 || echo "[publish] git sync failed (will retry next cycle)" >> logs/bot.log
