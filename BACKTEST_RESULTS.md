# Backtest results — strategy 8b vs the original strategy 8 vs buy & hold

Data: Binance BTCUSDT, **daily** candles, 2017–2026 (full available history).
Engine: `backtest.py` / `strategy8_replica.py` — signals on the daily close,
position applied on the next bar (no look-ahead), 0.10% fee + 0.05% slippage
charged on every position change, 100% of capital when long, long-only, no
leverage.

Reproduce with:

```bash
python3 backtest.py               # strategy 8b + equity curve
python3 strategy8_replica.py      # original strategy 8 vs 8b vs hold
```

## The key finding

Strategy 8 **as originally written** — enter when RSI crosses above the
threshold while price is above the EMA200, exit on a 3×ATR trailing stop —
did **NOT** beat buy & hold. Crossover entries miss most of the trend
(you only enter on the crossing event) and the trailing stop shakes you out.

Reformulating the same idea as a **state rule** fixes it:

> Be long **while** `close > EMA(200)` and `RSI(14) > 55`. Exit when the
> condition breaks. Re-enter when it holds again.

That reformulation is **strategy 8b** — the final strategy of this project.

## Headline results (2017–2026, 100% of capital)

| Metric | Strategy 8b | Buy & hold |
|---|---|---|
| Total return | **+3659%** | +1301% |
| Sharpe | **1.28** | 0.79 |
| Max drawdown | **−57%** | −83% |

## The honest nuance

Year by year, 8b beats holding in only **4 of 10 years**. In a pure bull
year, holding wins. The entire advantage comes from **losing little in the
crashes**:

| Year | Strategy 8b | Buy & hold |
|---|---|---|
| 2018 | **−36%** | −73% |
| 2022 | **−8%** | −64% |

Read it as **crash insurance with a modest edge**, not a money machine.
Avoiding the −70/−80% bear markets while capturing most of the bull runs is
what compounds into the headline numbers above.

Also remember: the historical total return is inflated by BTC's early
super-cycle. Expect the *shape* of the edge (protection, roughly half the
drawdown of holding) to persist — not the magnitude. The walk-forward
expectation is Sharpe ~0.5–0.7 (see `OPTIMIZATION.md`).

## Charts

`backtest.py` writes `output/equity_curve.png` (strategy vs hold, log scale)
from freshly downloaded data every time it runs.
