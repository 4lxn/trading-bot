#!/usr/bin/env python3
"""Execution bot for strategy 8b on Binance spot.

Rule: be LONG while close > EMA(200) and RSI(14) > 55 on the daily close;
otherwise be in cash. Long-only, spot, no leverage.

Design principles:
- IDEMPOTENT: every cycle reads the REAL current position from the exchange
  (or the paper state file in dry-run) and only acts if it disagrees with the
  signal. Safe to run every hour, after restarts, or twice by accident.
- Signals use only CLOSED daily candles — the forming candle is discarded.
- Three modes (env MODE): dry-run (default, paper position, no keys needed),
  testnet (Binance spot testnet, fake money), live (real money).
- Telegram notification on every state change, action and error.

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
PAPER_STATE_FILE = os.path.join(STATE_DIR, "paper_state.json")

DUST_USDT = 10.0  # base balance worth less than this counts as "no position"
CANDLES_NEEDED = 320  # EMA200 warm-up + margin


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
    return {
        "mode": os.environ.get("MODE", "dry-run").lower(),
        "api_key": os.environ.get("BINANCE_API_KEY", ""),
        "api_secret": os.environ.get("BINANCE_API_SECRET", ""),
        "symbol": os.environ.get("SYMBOL", "BTC/USDT"),
        "ema_len": int(os.environ.get("EMA_LEN", 200)),
        "rsi_len": int(os.environ.get("RSI_LEN", 14)),
        "rsi_threshold": float(os.environ.get("RSI_THRESHOLD", 55)),
        "order_frac": float(os.environ.get("ORDER_FRAC", 1.0)),
        "max_usdt": float(os.environ.get("MAX_USDT", 1000)),
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


def compute_signal(exchange: ccxt.binance, cfg: dict) -> tuple[bool, dict]:
    """Signal on the last CLOSED daily candle. Returns (is_long, info)."""
    ohlcv = exchange.fetch_ohlcv(cfg["symbol"], "1d", limit=CANDLES_NEEDED)
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.iloc[:-1]  # drop the still-forming candle
    if len(df) < cfg["ema_len"] + 20:
        raise RuntimeError(f"Not enough closed candles ({len(df)}) to warm up EMA{cfg['ema_len']}")
    close = df["close"].astype(float)
    ema_val = common.ema(close, cfg["ema_len"]).iloc[-1]
    rsi_val = common.rsi(close, cfg["rsi_len"]).iloc[-1]
    price = close.iloc[-1]
    is_long = price > ema_val and rsi_val > cfg["rsi_threshold"]
    info = {
        "candle": datetime.fromtimestamp(df["ts"].iloc[-1] / 1000, tz=timezone.utc).date(),
        "close": price,
        "ema": ema_val,
        "rsi": rsi_val,
    }
    return is_long, info


# ---------------------------------------------------------------------------
# Position state
# ---------------------------------------------------------------------------

def paper_state() -> dict:
    if os.path.exists(PAPER_STATE_FILE):
        with open(PAPER_STATE_FILE) as f:
            return json.load(f)
    return {"in_position": False, "btc": 0.0, "usdt": 1000.0}


def save_paper_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PAPER_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def read_position(exchange: ccxt.binance, cfg: dict, price: float) -> tuple[bool, float, float]:
    """Returns (in_position, base_amount, free_usdt) from the exchange."""
    base, quote = cfg["symbol"].split("/")
    balance = exchange.fetch_balance()
    base_amount = float(balance.get(base, {}).get("free", 0) or 0)
    free_quote = float(balance.get(quote, {}).get("free", 0) or 0)
    return base_amount * price > DUST_USDT, base_amount, free_quote


# ---------------------------------------------------------------------------
# One cycle
# ---------------------------------------------------------------------------

def run_cycle(cfg: dict) -> None:
    exchange = make_exchange(cfg)
    is_long, info = compute_signal(exchange, cfg)
    signal_txt = "LONG" if is_long else "OUT"
    log(f"[{cfg['mode']}] {cfg['symbol']} candle {info['candle']}: close {info['close']:,.0f}, "
        f"EMA{cfg['ema_len']} {info['ema']:,.0f}, RSI {info['rsi']:.1f} -> signal {signal_txt}")

    if cfg["mode"] == "dry-run":
        state = paper_state()
        in_position = state["in_position"]
        if is_long and not in_position:
            spend = min(state["usdt"] * cfg["order_frac"], cfg["max_usdt"])
            state.update(in_position=True, btc=spend / info["close"],
                         usdt=state["usdt"] - spend)
            save_paper_state(state)
            msg = (f"[dry-run] BUY signal: paper-bought {state['btc']:.6f} BTC "
                   f"at ~{info['close']:,.0f} ({spend:.2f} USDT)")
            log(msg)
            telegram(cfg, f"🟢 {msg}")
        elif not is_long and in_position:
            proceeds = state["btc"] * info["close"]
            msg = (f"[dry-run] SELL signal: paper-sold {state['btc']:.6f} BTC "
                   f"at ~{info['close']:,.0f} ({proceeds:.2f} USDT)")
            state.update(in_position=False, btc=0.0, usdt=state["usdt"] + proceeds)
            save_paper_state(state)
            log(msg)
            telegram(cfg, f"🔴 {msg}")
        else:
            log(f"[dry-run] Signal {signal_txt}, paper position already matches — nothing to do")
        return

    # testnet / live: read the REAL position, act only on mismatch (idempotent)
    in_position, base_amount, free_usdt = read_position(exchange, cfg, info["close"])
    if is_long and not in_position:
        spend = min(free_usdt * cfg["order_frac"], cfg["max_usdt"])
        if spend < DUST_USDT:
            log(f"BUY signal but only {free_usdt:.2f} USDT free — skipping")
            return
        amount = exchange.amount_to_precision(cfg["symbol"], spend / info["close"])
        order = exchange.create_market_buy_order(cfg["symbol"], float(amount))
        msg = (f"[{cfg['mode']}] BUY executed: {order.get('filled', amount)} "
               f"{cfg['symbol'].split('/')[0]} (~{spend:.2f} USDT)")
        log(msg)
        telegram(cfg, f"🟢 {msg}")
    elif not is_long and in_position:
        amount = exchange.amount_to_precision(cfg["symbol"], base_amount)
        order = exchange.create_market_sell_order(cfg["symbol"], float(amount))
        msg = (f"[{cfg['mode']}] SELL executed: {order.get('filled', amount)} "
               f"{cfg['symbol'].split('/')[0]} at ~{info['close']:,.0f}")
        log(msg)
        telegram(cfg, f"🔴 {msg}")
    else:
        log(f"Signal {signal_txt}, position already matches — nothing to do")


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
