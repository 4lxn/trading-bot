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

# bot_8b.py loads .env itself; exec so launchd tracks the real process
exec "$PYTHON" bot_8b.py >> logs/bot.log 2>&1
