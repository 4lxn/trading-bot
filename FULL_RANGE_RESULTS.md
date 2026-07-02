# Full-range validation + TradingView cross-check

> Re-verified 2026-07-02 on the pinned dataset
> `data/btcusdt_1d_verified_20260626.csv` — full evidence in
> `VERIFICATION.md`.

## Python backtest, full history (2017-08-17 → 2026-06-26)

Binance BTCUSDT daily, 100% of capital when long, fees + slippage included:

| Metric | Strategy 8b | Buy & hold |
|---|---|---|
| Total return | **+3164%** | +1303% |
| Sharpe | **1.23** | 0.79 |
| Max drawdown | **−58%** | −83% |

Restricted to 2018+ (skipping the 2017 super-cycle): 8b **+1254%** (Sharpe
1.06, MaxDD −33%) vs hold +349% (Sharpe 0.60, MaxDD −81%). The edge does
not depend on 2017.

## TradingView cross-check

An earlier run of the Pine implementation
(`strategies/08b_trend_rsi_state.pine`) on TradingView (spot data,
2018–2026 with TradingView's own 200-bar warm-up) showed the same
qualitative result: roughly **3× the return of holding with far smaller
drawdowns** (+2068% vs +603% on TradingView's window). Exact figures are
not directly comparable to the Python tables — TradingView starts trading
only after its indicator warm-up and uses its own fill model — but shape
and magnitude agree. Conclusion: **the Python code and the Pine strategy
implement the same rule**, and the edge is not an artifact of one engine.

To re-run the cross-check: open BTCUSDT (Binance) · 1D on TradingView, load
the Pine script, and compare the Strategy Tester's net profit / max
drawdown against `python3 backtest.py --start <date of TV's first trade>`.

## Current signal status (last close 2026-06-26)

The signal is **OUT (cash)**: BTC ~60k is below the EMA200 and RSI(14) ~30
is far below the 55 threshold. The strategy is sitting out the current
decline — exactly the behavior it is designed for. 2026 YTD: strategy 0%
vs hold −31%.

Check the live state any time with:

```bash
python3 backtest.py   # prints "Signal on last close: LONG / OUT (cash)"
```
