#!/usr/bin/env python3
"""Execution bot for strategy 8b on Binance spot — multi-ticker.

Rule per symbol: be LONG while close > EMA(200) and RSI(14) > 55 on the daily
close; otherwise be in cash. Long-only, spot, no leverage. With several
symbols (SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT) each one runs the rule
independently on an equal share of the capital — the validated portfolio
(see SWEEP_RESULTS.md).

Design principles:
- IDEMPOTENT: every cycle reads the REAL current position from the exchange
  (or the paper state file in dry-run) and only acts if it disagrees with the
  signal. Safe to run every hour, after restarts, or twice by accident.
- Signals use only CLOSED daily candles — the forming candle is discarded.
- Three modes (env MODE): dry-run (default, paper positions, no keys needed),
  testnet (Binance spot testnet, fake money), live (real money).
- Telegram notification on every state change, action and error.
- dry-run appends one row per daily candle to state/paper_equity.csv so the
  paper run can be compared against the backtest later.

Usage:
    python3 bot_8b.py            # one cycle, then exit (intended for launchd)
    python3 bot_8b.py --loop 3600  # keep running, one cycle per hour

Configuration via environment variables or a `.env` file — see .env.example.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import ccxt
import pandas as pd
import requests

import common

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "state")

DUST_USDT = 10.0  # base balance worth less than this counts as "no position"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_env_file(path: str = os.path.join(BASE_DIR, ".env")) -> None:
    """Minimal .env loader; real environment variables take precedence."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def config() -> dict:
    load_env_file()
    symbols_raw = os.environ.get("SYMBOLS", os.environ.get("SYMBOL", "BTC/USDT"))
    timeframe = os.environ.get("TIMEFRAME", "1d")
    sfx = "" if timeframe == "1d" else f"_{timeframe}"  # separate state per track
    return {
        "timeframe": timeframe,
        "paper_state_file": os.path.join(STATE_DIR, f"paper_state{sfx}.json"),
        "paper_equity_file": os.path.join(STATE_DIR, f"paper_equity{sfx}.csv"),
        "trades_file": os.path.join(STATE_DIR, f"trades{sfx}.csv"),
        "signals_file": os.path.join(STATE_DIR, f"signals{sfx}.json"),
        "hold_equity_file": os.path.join(STATE_DIR, f"hold_equity{sfx}.csv"),
        "hold_baseline_file": os.path.join(STATE_DIR, f"hold_baseline{sfx}.json"),
        "mode": os.environ.get("MODE", "dry-run").lower(),
        "api_key": os.environ.get("BINANCE_API_KEY", ""),
        "api_secret": os.environ.get("BINANCE_API_SECRET", ""),
        "symbols": [s.strip() for s in symbols_raw.split(",") if s.strip()],
        "ema_len": int(os.environ.get("EMA_LEN", 200)),
        "rsi_len": int(os.environ.get("RSI_LEN", 14)),
        "rsi_threshold": float(os.environ.get("RSI_THRESHOLD", 55)),
        "order_frac": float(os.environ.get("ORDER_FRAC", 1.0)),
        "max_usdt": float(os.environ.get("MAX_USDT", 1000)),
        "paper_usdt": float(os.environ.get("PAPER_USDT", 1000)),
        "tg_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "tg_chat": os.environ.get("TELEGRAM_CHAT_ID", ""),
    }


# ---------------------------------------------------------------------------
# Notifications & logging
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def telegram(cfg: dict, msg: str) -> None:
    if not cfg["tg_token"] or not cfg["tg_chat"]:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{cfg['tg_token']}/sendMessage",
            json={"chat_id": cfg["tg_chat"], "text": msg},
            timeout=10,
        )
    except Exception as e:  # notifications must never crash the bot
        log(f"Telegram error (ignored): {e}")


# ---------------------------------------------------------------------------
# Exchange
# ---------------------------------------------------------------------------

def make_exchange(cfg: dict) -> ccxt.binance:
    params = {"enableRateLimit": True}
    if cfg["mode"] != "dry-run":
        if not cfg["api_key"] or not cfg["api_secret"]:
            raise SystemExit(f"MODE={cfg['mode']} requires BINANCE_API_KEY and BINANCE_API_SECRET")
        params.update({"apiKey": cfg["api_key"], "secret": cfg["api_secret"]})
    exchange = ccxt.binance(params)
    if cfg["mode"] == "testnet":
        exchange.set_sandbox_mode(True)
    return exchange


def compute_signal(exchange: ccxt.binance, cfg: dict, symbol: str) -> tuple[bool, dict]:
    """Signal on the last CLOSED candle of cfg['timeframe']. Returns (is_long, info)."""
    # 3x the EMA span so the ewm warm-up matches the full-history backtest.
    needed = cfg["ema_len"] * 3 + 120
    tf_ms = exchange.parse_timeframe(cfg["timeframe"]) * 1000
    since = exchange.milliseconds() - needed * tf_ms
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, cfg["timeframe"], since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts")
    df = df.iloc[:-1]  # drop the still-forming candle
    if len(df) < cfg["ema_len"] + 20:
        raise RuntimeError(f"Not enough closed candles ({len(df)}) to warm up EMA{cfg['ema_len']}")
    close = df["close"].astype(float)
    ema_val = common.ema(close, cfg["ema_len"]).iloc[-1]
    rsi_val = common.rsi(close, cfg["rsi_len"]).iloc[-1]
    price = close.iloc[-1]
    is_long = price > ema_val and rsi_val > cfg["rsi_threshold"]
    stamp = datetime.fromtimestamp(df["ts"].iloc[-1] / 1000, tz=timezone.utc)

    def candle_key(ms):
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return str(d.date()) if cfg["timeframe"] == "1d" else d.strftime("%Y-%m-%d %H:%M")

    info = {
        # daily candles are identified by date; intraday ones need the time too
        "candle": stamp.date() if cfg["timeframe"] == "1d" else stamp.strftime("%Y-%m-%d %H:%M"),
        "close": price,
        "ema": ema_val,
        "rsi": rsi_val,
        # closes keyed by candle (same format as paper_equity's candle column),
        # used only to anchor the buy&hold benchmark to the paper start date.
        "closes_by_candle": {candle_key(ts): float(c)
                             for ts, c in zip(df["ts"], df["close"])},
    }
    return is_long, info


# ---------------------------------------------------------------------------
# Position state
# ---------------------------------------------------------------------------

def paper_state(cfg: dict) -> dict:
    """Per-symbol paper buckets: {symbol: {in_position, base, usdt}}.

    New symbols get an equal share of PAPER_USDT. The old single-symbol
    format ({"in_position", "btc", "usdt"}) is migrated to a BTC/USDT bucket.
    """
    state = {}
    if os.path.exists(cfg["paper_state_file"]):
        with open(cfg["paper_state_file"]) as f:
            state = json.load(f)
        if "btc" in state:  # pre-multi-ticker format
            state = {"BTC/USDT": {"in_position": state["in_position"],
                                  "base": state["btc"], "usdt": state["usdt"]}}
    share = cfg["paper_usdt"] / len(cfg["symbols"])
    for symbol in cfg["symbols"]:
        state.setdefault(symbol, {"in_position": False, "base": 0.0, "usdt": share})
    return state


def save_paper_state(cfg: dict, state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(cfg["paper_state_file"], "w") as f:
        json.dump(state, f, indent=2)


def log_paper_equity(cfg: dict, state: dict, prices: dict, candle) -> None:
    """One row per closed candle: per-symbol and total paper equity at the close."""
    path = cfg["paper_equity_file"]
    symbols = list(prices)
    values = [state[s]["usdt"] + state[s]["base"] * prices[s] for s in symbols]
    header = "candle," + ",".join(s.split("/")[0] for s in symbols) + ",total_usdt"
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()
        if lines and lines[0].strip() != header:  # SYMBOLS changed: keep old file aside
            os.rename(path, path + ".old")
        elif lines and lines[-1].startswith(str(candle)):
            return  # hourly reruns: this candle is already logged
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(header + "\n")
    total = sum(values)
    with open(path, "a") as f:
        f.write(f"{candle}," + ",".join(f"{v:.2f}" for v in values) + f",{total:.2f}\n")
    log(f"[dry-run] paper equity at {candle} close: {total:,.2f} USDT")


def update_hold_benchmark(cfg: dict, closes_by_symbol: dict, prices: dict, candle) -> None:
    """Track an equal-weight BUY & HOLD of the same symbols from the paper start,
    so the dashboard can show what NOT trading (just holding) would have earned.

    This is the honest benchmark for a market-timing strategy: the flat paper
    line only means something next to what holding would have done. Written to
    a separate file so it never disturbs the paper-equity schema. Cosmetic —
    wrapped by the caller so a failure here can never affect trading.
    """
    # Anchor the baseline to the FIRST paper candle (holding since day one).
    start_candle = str(candle)
    if os.path.exists(cfg["paper_equity_file"]):
        with open(cfg["paper_equity_file"]) as f:
            lines = f.readlines()
        if len(lines) > 1:
            start_candle = lines[1].split(",")[0]

    baseline = {}
    if os.path.exists(cfg["hold_baseline_file"]):
        with open(cfg["hold_baseline_file"]) as f:
            baseline = json.load(f)

    changed = False
    for sym in cfg["symbols"]:
        if sym in baseline:
            continue
        cbc = closes_by_symbol.get(sym, {})
        base_close = cbc.get(start_candle)
        if base_close is None and cbc:  # start predates fetch window: use oldest
            base_close = cbc[min(cbc)]
        if base_close:
            baseline[sym] = {"candle": start_candle, "close": base_close}
            changed = True
    if changed:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(cfg["hold_baseline_file"], "w") as f:
            json.dump(baseline, f, indent=2)

    if any(sym not in baseline for sym in cfg["symbols"]):
        return  # can't compute a complete benchmark yet

    share = cfg["paper_usdt"] / len(cfg["symbols"])

    def hold_total_at(candle_key: str):
        """Equal-weight hold value at a candle, from the fetched closes."""
        tot = 0.0
        for sym in cfg["symbols"]:
            close = closes_by_symbol.get(sym, {}).get(candle_key)
            if close is None:
                return None
            tot += share * close / baseline[sym]["close"]
        return tot

    now_total = hold_total_at(str(candle))
    if now_total is None:  # current candle not in fetched closes: use live prices
        now_total = sum(share * prices[sym] / baseline[sym]["close"] for sym in cfg["symbols"])

    path = cfg["hold_equity_file"]
    header = "candle,total_usdt"
    if os.path.exists(path):
        with open(path) as f:
            lines = f.readlines()
        if lines and lines[0].strip() != header:
            os.rename(path, path + ".old")
        elif lines and lines[-1].startswith(str(candle)):
            return  # this candle already logged (idempotent on hourly reruns)

    if not os.path.exists(path):
        # One-time backfill: reconstruct the benchmark for every candle the
        # strategy already logged, so the hold line matches the strategy
        # history from day one (the bot fetched enough closes to do it).
        with open(path, "w") as f:
            f.write(header + "\n")
            if os.path.exists(cfg["paper_equity_file"]):
                with open(cfg["paper_equity_file"]) as pf:
                    past = [l.split(",")[0] for l in pf.read().splitlines()[1:]]
                for c in past:
                    if c == str(candle):
                        continue
                    val = hold_total_at(c)
                    if val is not None:
                        f.write(f"{c},{val:.2f}\n")

    with open(path, "a") as f:
        f.write(f"{candle},{now_total:.2f}\n")


def log_trade(cfg: dict, symbol: str, side: str, price: float, amount: float,
              value: float, candle) -> None:
    """Append one row per executed action so the dashboard can show the
    full trade history (state/trades{sfx}.csv, published to docs/)."""
    path = cfg["trades_file"]
    os.makedirs(STATE_DIR, exist_ok=True)
    is_new = not os.path.exists(path)
    with open(path, "a") as f:
        if is_new:
            f.write("ts_utc,candle,symbol,side,price,amount,value_usdt,mode\n")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts},{candle},{symbol},{side},{price:.8g},{amount:.8g},"
                f"{value:.2f},{cfg['mode']}\n")


def save_signals(cfg: dict, snapshot: dict) -> None:
    """Per-symbol signal context (close vs EMA, RSI vs threshold, position)
    so the dashboard can show WHY the bot is in or out, not just the equity."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(cfg["signals_file"], "w") as f:
        json.dump({
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "mode": cfg["mode"],
            "timeframe": cfg["timeframe"],
            "rule": f"close > EMA({cfg['ema_len']}) and RSI({cfg['rsi_len']}) "
                    f"> {cfg['rsi_threshold']:g}",
            "symbols": snapshot,
        }, f, indent=2)


def read_position(exchange: ccxt.binance, symbol: str, price: float) -> tuple[bool, float, float]:
    """Returns (in_position, base_amount, free_usdt) from the exchange."""
    base, quote = symbol.split("/")
    balance = exchange.fetch_balance()
    base_amount = float(balance.get(base, {}).get("free", 0) or 0)
    free_quote = float(balance.get(quote, {}).get("free", 0) or 0)
    return base_amount * price > DUST_USDT, base_amount, free_quote


# ---------------------------------------------------------------------------
# One cycle
# ---------------------------------------------------------------------------

def paper_symbol_cycle(cfg: dict, state: dict, symbol: str, is_long: bool, info: dict) -> bool:
    bucket = state[symbol]
    base = symbol.split("/")[0]
    # Same friction the backtest charges (fee + slippage per side), so the
    # paper equity curve stays comparable to it.
    friction = 1 - (common.DEFAULT_FEE + common.DEFAULT_SLIPPAGE)
    if is_long and not bucket["in_position"]:
        spend = min(bucket["usdt"] * cfg["order_frac"], cfg["max_usdt"])
        bucket.update(in_position=True, base=spend * friction / info["close"],
                      usdt=bucket["usdt"] - spend)
        save_paper_state(cfg, state)
        log_trade(cfg, symbol, "BUY", info["close"], bucket["base"], spend, info["candle"])
        msg = (f"[dry-run] BUY signal: paper-bought {bucket['base']:.6f} {base} "
               f"at ~{info['close']:,.2f} ({spend:.2f} USDT)")
        log(msg)
        telegram(cfg, f"🟢 {msg}")
    elif not is_long and bucket["in_position"]:
        sold = bucket["base"]
        proceeds = sold * info["close"] * friction
        msg = (f"[dry-run] SELL signal: paper-sold {sold:.6f} {base} "
               f"at ~{info['close']:,.2f} ({proceeds:.2f} USDT)")
        bucket.update(in_position=False, base=0.0, usdt=bucket["usdt"] + proceeds)
        save_paper_state(cfg, state)
        log_trade(cfg, symbol, "SELL", info["close"], sold, proceeds, info["candle"])
        log(msg)
        telegram(cfg, f"🔴 {msg}")
    else:
        log(f"[dry-run] {symbol} signal {'LONG' if is_long else 'OUT'}, "
            f"paper position already matches — nothing to do")
    return bucket["in_position"]


def real_symbol_cycle(exchange: ccxt.binance, cfg: dict, symbol: str,
                      is_long: bool, info: dict) -> bool:
    """testnet / live: read the REAL position, act only on mismatch (idempotent)."""
    in_position, base_amount, free_usdt = read_position(exchange, symbol, info["close"])
    if is_long and not in_position:
        spend = min(free_usdt * cfg["order_frac"], cfg["max_usdt"])
        if spend < DUST_USDT:
            log(f"{symbol} BUY signal but only {free_usdt:.2f} USDT free — skipping")
            return in_position
        amount = exchange.amount_to_precision(symbol, spend / info["close"])
        order = exchange.create_market_buy_order(symbol, float(amount))
        filled = float(order.get("filled") or amount)
        log_trade(cfg, symbol, "BUY", info["close"], filled, spend, info["candle"])
        msg = (f"[{cfg['mode']}] BUY executed: {filled} "
               f"{symbol.split('/')[0]} (~{spend:.2f} USDT)")
        log(msg)
        telegram(cfg, f"🟢 {msg}")
        return True
    elif not is_long and in_position:
        amount = exchange.amount_to_precision(symbol, base_amount)
        order = exchange.create_market_sell_order(symbol, float(amount))
        filled = float(order.get("filled") or amount)
        log_trade(cfg, symbol, "SELL", info["close"], filled,
                  filled * info["close"], info["candle"])
        msg = (f"[{cfg['mode']}] SELL executed: {filled} "
               f"{symbol.split('/')[0]} at ~{info['close']:,.2f}")
        log(msg)
        telegram(cfg, f"🔴 {msg}")
        return False
    else:
        log(f"{symbol} signal {'LONG' if is_long else 'OUT'}, position already matches — nothing to do")
    return in_position


def run_cycle(cfg: dict) -> None:
    exchange = make_exchange(cfg)
    state = paper_state(cfg) if cfg["mode"] == "dry-run" else None
    prices, last_candle, snapshot, closes_by_symbol = {}, None, {}, {}
    for symbol in cfg["symbols"]:
        is_long, info = compute_signal(exchange, cfg, symbol)
        prices[symbol], last_candle = info["close"], info["candle"]
        closes_by_symbol[symbol] = info.pop("closes_by_candle", {})
        log(f"[{cfg['mode']}] {symbol} {cfg['timeframe']} candle {info['candle']}: "
            f"close {info['close']:,.2f}, EMA{cfg['ema_len']} {info['ema']:,.2f}, "
            f"RSI {info['rsi']:.1f} -> signal {'LONG' if is_long else 'OUT'}")
        if cfg["mode"] == "dry-run":
            in_position = paper_symbol_cycle(cfg, state, symbol, is_long, info)
        else:
            in_position = real_symbol_cycle(exchange, cfg, symbol, is_long, info)
        snapshot[symbol] = {
            "signal": "LONG" if is_long else "OUT",
            "in_position": in_position,
            "candle": str(info["candle"]),
            "close": round(info["close"], 8),
            "ema": round(info["ema"], 8),
            "rsi": round(info["rsi"], 1),
            "ema_dist_pct": round((info["close"] / info["ema"] - 1) * 100, 2),
        }
    save_signals(cfg, snapshot)
    if cfg["mode"] == "dry-run":
        save_paper_state(cfg, state)
        log_paper_equity(cfg, state, prices, last_candle)
    # Buy&hold benchmark — cosmetic, must never break the trading cycle.
    try:
        update_hold_benchmark(cfg, closes_by_symbol, prices, last_candle)
    except Exception as e:
        log(f"hold benchmark error (ignored): {e}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--loop", type=int, metavar="SECONDS",
                   help="Run forever, one cycle every SECONDS (default: single cycle)")
    args = p.parse_args()

    cfg = config()
    if cfg["mode"] not in ("dry-run", "testnet", "live"):
        raise SystemExit(f"Invalid MODE '{cfg['mode']}' (use dry-run, testnet or live)")
    if cfg["mode"] == "live":
        log("MODE=live — trading with REAL money")

    while True:
        try:
            run_cycle(cfg)
        except Exception as e:
            log(f"ERROR: {e}")
            telegram(cfg, f"⚠️ bot_8b error: {e}")
            if not args.loop:
                sys.exit(1)
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
