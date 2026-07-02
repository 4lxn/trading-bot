# bot_8b.py — running strategy 8b 24/7

Executes the validated 8b rule on Binance spot: **long while
`close > EMA(200)` and `RSI(14) > 55` on the daily close; otherwise cash.**
Long-only, no leverage, no liquidation risk.

## Safety design

- **Idempotent.** Every cycle reads the *real* position from the exchange and
  only acts when it disagrees with the signal. Running it every hour, twice in
  a row, or right after a reboot never double-buys or double-sells.
- **Closed candles only.** The still-forming daily candle is discarded, so the
  signal never flip-flops intraday.
- **Three modes**, promoted in order and never skipped:
  1. `dry-run` (default) — no keys needed; paper position in `state/paper_state.json`.
  2. `testnet` — Binance Spot testnet, fake money (keys from https://testnet.binance.vision).
  3. `live` — real money. Only after **weeks** of clean dry-run + testnet logs.
- **Telegram** message on every buy, sell and error.
- API keys must be created **without withdrawal permission**.

## Setup

```bash
cd ~/trading-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env     # then edit .env: mode, keys, sizing, Telegram
```

Position sizing is controlled in `.env`:

- `ORDER_FRAC` — fraction of free USDT deployed on a buy (1.0 = the backtest).
- `MAX_USDT` — hard cap per buy order. Start small.

## Run manually

```bash
./run.sh                       # one cycle: log the signal, act if needed
python3 bot_8b.py --loop 3600  # alternative: keep running, hourly cycles
```

Each cycle logs one line like:

```
[2026-07-02 10:05:01 UTC] [dry-run] BTC/USDT candle 2026-07-01: close 60,123, EMA200 79,041, RSI 29.3 -> signal OUT
```

## Run 24/7 on the Mac mini (launchd)

`launchd/com.trading8b.bot.plist` runs `run.sh` **hourly** and on boot.
Hourly is deliberate: the signal only changes once a day, but hourly runs
make the bot robust to sleep, reboots and exchange downtime — idempotency
makes the extra runs free.

```bash
# 1. Edit the plist: replace both /Users/YOURUSER/trading-bot paths
#    with the real path to this repo on the Mac.
nano launchd/com.trading8b.bot.plist

# 2. Install and load it
cp launchd/com.trading8b.bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trading8b.bot.plist

# 3. Verify
launchctl list | grep trading8b
tail -f logs/bot.log
```

To stop it: `launchctl unload ~/Library/LaunchAgents/com.trading8b.bot.plist`.

Also disable system sleep (or enable *Wake for network access* +
`caffeinate`): System Settings → Energy Saver → prevent automatic sleeping.

## Go-live checklist

1. Weeks of `MODE=dry-run` — logs and Telegram messages look right.
2. Weeks of `MODE=testnet` — orders fill correctly on the testnet.
3. `MODE=live` with a **small `MAX_USDT`**, keys without withdrawal rights.
4. Review `logs/bot.log` weekly; log paper trades in `paper_trading_8b.xlsx`
   in parallel and compare.
5. Expect drawdowns of −30% to −50%. If that number is not survivable,
   lower `ORDER_FRAC` *before* going live, not during the drawdown.

This is educational material, not financial advice. The decisions and the
risk are yours.
