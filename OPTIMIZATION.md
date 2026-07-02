# Parameter optimization — grid search + walk-forward

Script: `optimize.py`. Data: Binance BTCUSDT daily, 2017–2026.

```bash
python3 optimize.py
```

## Grid search (full sample)

Grid: EMA length {50, 100, 150, 200, 250, 300} × RSI threshold
{40, 45, 50, 55, 60, 65, 70}, Sharpe and total return per cell.
Outputs `output/heatmap_sharpe.png` and `output/heatmap_return.png`.

**Best parameters: RSI threshold 55, EMA 200.**

The important result is not the single best cell but its neighborhood: the
good region is a **wide plateau**, not an isolated spike. Neighboring
parameters (EMA 150–250, RSI 50–60) perform similarly. That is what a robust
strategy looks like; an isolated spike would mean the parameters were
overfit to noise.

## Walk-forward validation

To estimate honest forward performance, `optimize.py` repeatedly picks the
best in-sample parameters on a training window and applies them to the
following unseen year, then stitches the out-of-sample segments together.

**Realistic forward expectation: Sharpe ~0.5–0.7, with roughly half the
drawdown of buy & hold.**

This is deliberately lower than the full-sample Sharpe of 1.28 — the
full-sample number benefits from choosing parameters with hindsight and from
BTC's early super-cycle. Plan position sizing around the walk-forward
numbers, not the headline ones.
