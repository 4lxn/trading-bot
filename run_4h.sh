#!/bin/bash
# 4h curiosity track: same portfolio, best 4h config from SWEEP_RESULTS.md
# (EMA 600 bars / RSI 84 > 50). PERMANENTLY dry-run — the backtest already
# showed 4h loses to daily; this exists to watch that live, never to trade.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p logs

export MODE=dry-run          # hard safety: never inherits testnet/live from .env
export TIMEFRAME=4h
export SYMBOLS="BTC/USDT,ETH/USDT,SOL/USDT"
export EMA_LEN=600
export RSI_LEN=84
export RSI_THRESHOLD=50
export PAPER_USDT=1000

if [ -x ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
else
    PYTHON="python3"
fi

"$PYTHON" bot_8b.py >> logs/bot_4h.log 2>&1
# No publish step here: run.sh is the single publisher (avoids git races).
