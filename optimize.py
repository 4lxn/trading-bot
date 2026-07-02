#!/usr/bin/env python3
"""Parameter optimization for strategy 8b: grid search + walk-forward validation.

Two parts:
1. Full-sample grid search over EMA length x RSI threshold. The point is NOT
   to pick the single best cell but to check that good parameters form a wide
   plateau (robust) rather than an isolated spike (overfit).
   Outputs: output/heatmap_sharpe.png, output/heatmap_return.png
2. Walk-forward: repeatedly pick the best in-sample parameters on a training
   window, then apply them to the following unseen year. The stitched
   out-of-sample equity curve is the honest expectation of forward performance.

Usage:
    python3 optimize.py
    python3 optimize.py --train-years 3 --test-years 1
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import common

EMA_GRID = [50, 100, 150, 200, 250, 300]
RSI_GRID = [40, 45, 50, 55, 60, 65, 70]


def grid_search(df: pd.DataFrame, fee: float, slippage: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    sharpe_grid = pd.DataFrame(index=EMA_GRID, columns=RSI_GRID, dtype=float)
    return_grid = pd.DataFrame(index=EMA_GRID, columns=RSI_GRID, dtype=float)
    for ema_len in EMA_GRID:
        for th in RSI_GRID:
            signal = common.state_signal(df, ema_len, 14, th)
            result = common.run_backtest(df, signal, fee, slippage)
            stats = common.summarize(result)
            sharpe_grid.loc[ema_len, th] = stats["sharpe"]
            return_grid.loc[ema_len, th] = stats["total_return"]
    return sharpe_grid, return_grid


def plot_heatmap(grid: pd.DataFrame, title: str, fmt: str, path: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.imshow(grid.values.astype(float), cmap="viridis", aspect="auto")
    ax.set_xticks(range(len(grid.columns)), [str(c) for c in grid.columns])
    ax.set_yticks(range(len(grid.index)), [str(i) for i in grid.index])
    ax.set_xlabel("RSI threshold")
    ax.set_ylabel("EMA length")
    ax.set_title(title)
    for i in range(len(grid.index)):
        for j in range(len(grid.columns)):
            ax.text(j, i, format(grid.values[i, j], fmt), ha="center", va="center",
                    color="white", fontsize=8)
    fig.colorbar(im, ax=ax)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    print(f"Saved {path}")


def walk_forward(df: pd.DataFrame, fee: float, slippage: float,
                 train_years: int, test_years: int) -> None:
    years = sorted(df.index.year.unique())
    oos_returns = []
    print("\nWalk-forward (best in-sample params applied to the next unseen window):")
    for start in range(0, len(years) - train_years, test_years):
        train_y = years[start:start + train_years]
        test_y = years[start + train_years:start + train_years + test_years]
        if not test_y:
            break
        train = df[df.index.year.isin(train_y)]
        best, best_sharpe = None, -np.inf
        for ema_len in EMA_GRID:
            for th in RSI_GRID:
                signal = common.state_signal(df, ema_len, 14, th)
                result = common.run_backtest(train, signal.loc[train.index], fee, slippage)
                s = common.sharpe(result["strategy_ret"])
                if s > best_sharpe:
                    best, best_sharpe = (ema_len, th), s
        test = df[df.index.year.isin(test_y)]
        signal = common.state_signal(df, best[0], 14, best[1])
        result = common.run_backtest(test, signal.loc[test.index], fee, slippage)
        oos_returns.append(result["strategy_ret"])
        ret = result["equity"].iloc[-1] - 1
        hold = result["hold_equity"].iloc[-1] - 1
        print(f"  train {train_y[0]}-{train_y[-1]} -> test {test_y[0]}-{test_y[-1]}: "
              f"best EMA {best[0]}, RSI > {best[1]} (IS Sharpe {best_sharpe:.2f}) | "
              f"OOS {ret:+.1%} vs hold {hold:+.1%}")

    if oos_returns:
        stitched = pd.concat(oos_returns)
        equity = (1 + stitched).cumprod()
        print("\nStitched out-of-sample results:")
        print(f"  Total return : {equity.iloc[-1] - 1:+.1%}")
        print(f"  Sharpe       : {common.sharpe(stitched):.2f}")
        print(f"  Max drawdown : {common.max_drawdown(equity):.1%}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", help="OHLCV CSV path")
    p.add_argument("--symbol", default=common.DEFAULT_SYMBOL)
    p.add_argument("--fee", type=float, default=common.DEFAULT_FEE)
    p.add_argument("--slippage", type=float, default=common.DEFAULT_SLIPPAGE)
    p.add_argument("--train-years", type=int, default=3)
    p.add_argument("--test-years", type=int, default=1)
    args = p.parse_args()

    df = common.load_data(csv=args.csv, symbol=args.symbol)
    os.makedirs(common.OUTPUT_DIR, exist_ok=True)

    print(f"{args.symbol} daily, {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"Grid: EMA {EMA_GRID} x RSI threshold {RSI_GRID}\n")

    sharpe_grid, return_grid = grid_search(df, args.fee, args.slippage)
    print("Sharpe by (EMA length x RSI threshold):")
    print(sharpe_grid.round(2).to_string())
    best = sharpe_grid.stack().idxmax()
    print(f"\nBest full-sample Sharpe: EMA {best[0]}, RSI > {best[1]} "
          f"({sharpe_grid.loc[best]:.2f}) — check it sits on a plateau, not a spike.")

    plot_heatmap(sharpe_grid, "Sharpe — strategy 8b parameter grid", ".2f",
                 os.path.join(common.OUTPUT_DIR, "heatmap_sharpe.png"))
    plot_heatmap(return_grid * 100, "Total return % — strategy 8b parameter grid", ".0f",
                 os.path.join(common.OUTPUT_DIR, "heatmap_return.png"))

    walk_forward(df, args.fee, args.slippage, args.train_years, args.test_years)


if __name__ == "__main__":
    main()
