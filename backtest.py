#!/usr/bin/env python3
"""Backtest strategy 8b (trend + RSI state rule) on daily data.

Rule: be long while close > EMA(200) AND RSI(14) > 55; flat otherwise.
Long-only, no leverage, 100% of capital when in position.

Usage:
    python3 backtest.py                     # BTC/USDT daily, downloads data if needed
    python3 backtest.py --start 2018-01-01  # restrict the test window
    python3 backtest.py --ema 200 --threshold 55
    python3 backtest.py --csv data/btcusdt_1d.csv

Outputs a metrics summary, a year-by-year table, and output/equity_curve.png.
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", help="OHLCV CSV path (default: data/<symbol>_1d.csv, auto-downloaded)")
    p.add_argument("--symbol", default=common.DEFAULT_SYMBOL)
    p.add_argument("--start", help="Only test from this date (YYYY-MM-DD)")
    p.add_argument("--end", help="Only test up to this date (YYYY-MM-DD)")
    p.add_argument("--ema", type=int, default=200, help="EMA length (default 200)")
    p.add_argument("--rsi-len", type=int, default=14, help="RSI length (default 14)")
    p.add_argument("--threshold", type=float, default=55, help="RSI threshold (default 55)")
    p.add_argument("--fee", type=float, default=common.DEFAULT_FEE)
    p.add_argument("--slippage", type=float, default=common.DEFAULT_SLIPPAGE)
    p.add_argument("--refresh", action="store_true", help="Re-download data even if cached")
    args = p.parse_args()

    df = common.load_data(csv=args.csv, symbol=args.symbol, refresh=args.refresh)

    # Compute indicators on the FULL history so the EMA200 is already warmed up
    # at the start of a restricted window, then slice.
    signal = common.state_signal(df, args.ema, args.rsi_len, args.threshold)
    if args.start:
        df, signal = df.loc[args.start:], signal.loc[args.start:]
    if args.end:
        df, signal = df.loc[:args.end], signal.loc[:args.end]

    result = common.run_backtest(df, signal, fee=args.fee, slippage=args.slippage)

    print(f"\n{args.symbol} daily, {result.index[0].date()} -> {result.index[-1].date()}")
    print(f"Rule: long while close > EMA({args.ema}) and RSI({args.rsi_len}) > {args.threshold}\n")
    common.print_summary(common.summarize(result, "strategy 8b"))
    common.print_summary(common.summarize_hold(result))

    print("\nYear by year:")
    table = common.yearly_table(result)
    for year, row in table.iterrows():
        marker = "beats hold" if row["beats_hold"] else ""
        print(f"  {year}: strategy {row['strategy']:+8.1%}   hold {row['hold']:+8.1%}   {marker}")
    print(f"\nBeats hold in {int(table['beats_hold'].sum())} of {len(table)} years.")

    # Current signal state (last closed candle)
    last = result.iloc[-1]
    state = "LONG" if last["signal"] else "OUT (cash)"
    print(f"\nSignal on last close ({result.index[-1].date()}): {state}")

    os.makedirs(common.OUTPUT_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(result.index, result["equity"], label="Strategy 8b", linewidth=1.2)
    ax.plot(result.index, result["hold_equity"], label="Buy & hold", linewidth=1.2, alpha=0.7)
    ax.set_yscale("log")
    ax.set_title(f"Strategy 8b vs buy & hold — {args.symbol} daily "
                 f"(EMA {args.ema}, RSI > {args.threshold:g})")
    ax.set_ylabel("Equity (log scale, start = 1)")
    ax.legend()
    ax.grid(alpha=0.3)
    out = os.path.join(common.OUTPUT_DIR, "equity_curve.png")
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Equity curve saved to {out}")


if __name__ == "__main__":
    main()
