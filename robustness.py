#!/usr/bin/env python3
"""Robustness checks for strategy 8b — run these before trusting any backtest.

A strategy is never "optimal"; the realistic bar is ROBUST:
1. Survives higher costs (fees + slippage stress).
2. Survives late execution (signal applied 1-3 days later).
3. Every ingredient earns its place (EMA200 alone vs EMA200 + RSI).
4. Works across sub-windows, not just the full-history super-cycle.

Combined with optimize.py (parameter plateau + walk-forward out-of-sample),
this is the evidence base for going to paper trading.

Usage:
    python3 robustness.py
    python3 robustness.py --csv data/btcusdt_1d_verified_20260626.csv
"""

import argparse

import common


def report(tag: str, result) -> None:
    s = common.summarize(result)
    print(f"  {tag:44s} ret {s['total_return']:+9.1%}  Sharpe {s['sharpe']:.2f}  "
          f"MaxDD {s['max_drawdown']:.1%}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", help="OHLCV CSV path")
    p.add_argument("--symbol", default=common.DEFAULT_SYMBOL)
    args = p.parse_args()

    df = common.load_data(csv=args.csv, symbol=args.symbol)
    sig = common.state_signal(df)
    print(f"{args.symbol} daily, {df.index[0].date()} -> {df.index[-1].date()}\n")

    print("1. Cost stress (per side):")
    for fee, slip in [(0.001, 0.0005), (0.002, 0.001), (0.003, 0.002)]:
        report(f"fee {fee:.1%} + slippage {slip:.2%}",
               common.run_backtest(df, sig, fee, slip))

    print("\n2. Execution delay:")
    for lag in [1, 2, 3]:
        delayed = sig.shift(lag - 1).fillna(False)  # engine already shifts by 1
        report(f"execute {lag} day(s) after the signal",
               common.run_backtest(df, delayed))

    print("\n3. Ingredient check — does the RSI filter earn its place?")
    ema_only = df["close"] > common.ema(df["close"], 200)
    report("EMA200 only (close > EMA200)", common.run_backtest(df, ema_only))
    report("8b (EMA200 + RSI(14) > 55)", common.run_backtest(df, sig))

    print("\n4. Sub-windows (indicators warmed up on full history):")
    for start in ["2018-01-01", "2020-01-01", "2022-01-01"]:
        res = common.run_backtest(df.loc[start:], sig.loc[start:])
        st, hold = common.summarize(res), common.summarize_hold(res)
        print(f"  from {start}:  8b {st['total_return']:+9.1%} "
              f"(Sharpe {st['sharpe']:.2f}, DD {st['max_drawdown']:.0%})   "
              f"hold {hold['total_return']:+9.1%} "
              f"(Sharpe {hold['sharpe']:.2f}, DD {hold['max_drawdown']:.0%})")

    print("\nPass criteria: Sharpe stays above hold and drawdown stays well below"
          "\nhold in every row. If a single row breaks the strategy, it was luck.")


if __name__ == "__main__":
    main()
