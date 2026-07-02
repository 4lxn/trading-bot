# Full-range validation + TradingView cross-check

## Python backtest, full history (2017–2026)

Binance BTCUSDT daily, 100% of capital when long, fees + slippage included:

| Metric | Strategy 8b | Buy & hold |
|---|---|---|
| Total return | **+3659%** | +1301% |
| Sharpe | **1.28** | 0.79 |
| Max drawdown | **−57%** | −83% |

## TradingView cross-check (2018–2026)

The Pine implementation (`strategies/08b_trend_rsi_state.pine`) was run on
TradingView against real spot data over 2018–2026:

| Source | Strategy 8b | Buy & hold |
|---|---|---|
| TradingView (spot, 2018–2026) | **+2068%** | +603% |
| Python engine, same window | **+2362%** | — |

The two implementations agree to within normal execution-model differences
(TradingView fills at next open with its own slippage model). Conclusion:
**the Python code is a faithful replica of the Pine strategy**, and the edge
is not an artifact of one engine.

## Current signal status (as of July 2026)

The signal is **OUT (cash)**: BTC ~60k is below the EMA200 (~79k) and
RSI(14) ~29 is far below the 55 threshold. The strategy is sitting out the
current decline — exactly the behavior it is designed for.

Check the live state any time with:

```bash
python3 backtest.py   # prints "Signal on last close: LONG / OUT (cash)"
```
