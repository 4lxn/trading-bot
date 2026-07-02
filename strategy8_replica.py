#!/usr/bin/env python3
"""Faithful replica of the ORIGINAL strategy 8 (event entry + ATR trailing stop),
compared against strategy 8b (state rule) and buy & hold.

This script exists to document the key finding of the project:

  Strategy 8 as originally written — enter when RSI crosses above the
  threshold while price is above the EMA200, exit on an ATR trailing stop —
  does NOT beat buy & hold. Reformulating the same idea as a STATE rule
  ("be long while close > EMA200 and RSI > 55") is what creates the edge.
  That reformulation is strategy 8b.

Usage:
    python3 strategy8_replica.py
"""

import argparse

import numpy as np
import pandas as pd

import common


def strategy8_signal(df: pd.DataFrame, ema_len: int = 200, rsi_len: int = 14,
                     rsi_threshold: float = 55, atr_len: int = 14,
                     atr_mult: float = 3.0) -> pd.Series:
    """Original strategy 8: crossover entry + ATR trailing stop exit.

    Entry : RSI crosses above the threshold while close > EMA(ema_len).
    Exit  : close falls below the trailing stop (highest close since entry
            minus atr_mult * ATR), or below the EMA.
    """
    ema = common.ema(df["close"], ema_len)
    rsi = common.rsi(df["close"], rsi_len)
    atr = common.atr(df, atr_len)

    entry = (rsi > rsi_threshold) & (rsi.shift(1) <= rsi_threshold) & (df["close"] > ema)

    in_pos = False
    highest = 0.0
    signal = np.zeros(len(df), dtype=bool)
    for i in range(len(df)):
        close = df["close"].iloc[i]
        if in_pos:
            highest = max(highest, close)
            stop = highest - atr_mult * atr.iloc[i]
            if close < stop or close < ema.iloc[i]:
                in_pos = False
        elif entry.iloc[i]:
            in_pos = True
            highest = close
        signal[i] = in_pos
    return pd.Series(signal, index=df.index)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", help="OHLCV CSV path")
    p.add_argument("--symbol", default=common.DEFAULT_SYMBOL)
    p.add_argument("--atr-mult", type=float, default=3.0)
    args = p.parse_args()

    df = common.load_data(csv=args.csv, symbol=args.symbol)
    print(f"{args.symbol} daily, {df.index[0].date()} -> {df.index[-1].date()}\n")

    sig8 = strategy8_signal(df, atr_mult=args.atr_mult)
    res8 = common.run_backtest(df, sig8)
    common.print_summary(common.summarize(res8, "strategy 8 (original: crossover entry + ATR trail)"))

    sig8b = common.state_signal(df)
    res8b = common.run_backtest(df, sig8b)
    common.print_summary(common.summarize(res8b, "strategy 8b (state rule)"))

    common.print_summary(common.summarize_hold(res8))

    print("\nConclusion: the edge comes from the STATE formulation (8b), "
          "not from the crossover-entry version (8).")


if __name__ == "__main__":
    main()
