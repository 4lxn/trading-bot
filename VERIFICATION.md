# Verification — do we have solid foundations?

Date: 2026-07-02. Everything below was re-run from scratch with this repo's
engine on **real Binance BTCUSDT daily data supplied independently**
(CryptoDataDownload export, 2017-08-17 → 2026-06-26, 3,213 candles), pinned
at `data/btcusdt_1d_verified_20260626.csv` so every number here is
reproducible:

```bash
python3 backtest.py           --csv data/btcusdt_1d_verified_20260626.csv
python3 strategy8_replica.py  --csv data/btcusdt_1d_verified_20260626.csv
python3 optimize.py           --csv data/btcusdt_1d_verified_20260626.csv
python3 robustness.py         --csv data/btcusdt_1d_verified_20260626.csv
```

**First, the honest framing: no strategy is "optimal".** Optimal is not a
provable property of a trading rule — anyone claiming it is overfitting.
What CAN be verified is **robustness**, which is what actually predicts
forward survival. That is what this document checks, in six tests.

## 1. Headline result (2017-08-17 → 2026-06-26, 100% of capital)

| Metric | Strategy 8b | Buy & hold |
|---|---|---|
| Total return | **+3164%** | +1303% |
| CAGR | **+48.2%** | +34.7% |
| Sharpe | **1.23** | 0.79 |
| Max drawdown | **−58.0%** | −83.2% |
| Exposure | 32.9% | 100% |
| Trades | 101 (win rate 35%) | 1 |

Year by year (✓ = beats hold):

| Year | 8b | Hold | |
|---|---|---|---|
| 2017 | +141.0% | +220.1% | |
| 2018 | **−33.1%** | −73.0% | ✓ |
| 2019 | +103.7% | +94.3% | ✓ |
| 2020 | +145.2% | +302.0% | |
| 2021 | +82.4% | +59.8% | ✓ |
| 2022 | **−8.1%** | −64.2% | ✓ |
| 2023 | +44.9% | +155.6% | |
| 2024 | +59.5% | +121.3% | |
| 2025 | +4.7% | −6.3% | ✓ |
| 2026 | +0.0% | −31.4% | ✓ |

The story is unchanged: **all of the edge comes from losing little in bad
years** (2018, 2022, 2025, 2026) while capturing enough of the bulls. In
pure bull years, holding wins. This is crash insurance with a modest edge.

## 2. The key finding still holds (strategy 8 vs 8b)

| Full range | Return | Sharpe | MaxDD |
|---|---|---|---|
| Strategy 8 (crossover entry + ATR trail) | +1023% | 0.87 | −65.6% |
| Strategy 8b (state rule) | **+3164%** | **1.23** | **−58.0%** |
| Buy & hold | +1303% | 0.79 | −83.2% |

The original strategy 8 **loses to buy & hold on total return**. The state
reformulation (8b) is what wins. Confirmed on independent data.

## 3. Parameter plateau (not a lucky spike)

Sharpe over the grid EMA {50…300} × RSI threshold {40…70}: the **RSI 55
column is best across every EMA length** (1.20–1.27), and the EMA length
barely matters. Our parameters (EMA 200, RSI 55, Sharpe 1.23) sit on a wide
plateau; the single best cell (EMA 300, 1.27) is not meaningfully better.
Exactly what a robust — not overfit — parameter choice looks like.
Heatmaps: `output/heatmap_sharpe.png`, `output/heatmap_return.png`.

## 4. Walk-forward (out-of-sample, the honest forward estimate)

Re-optimizing on 3 years and trading the following unseen year, 2020→2026
stitched together:

| 2020–2026 | Out-of-sample 8b | Buy & hold |
|---|---|---|
| Total return | +456% | +735% |
| Sharpe | **0.94** | 0.85 |
| Max drawdown | **−44.4%** | −76.6% |

Out of sample the strategy earns **less raw return than holding in a
bull-heavy window** but with better Sharpe and barely half the drawdown —
consistent with everything above. Keep planning around **forward Sharpe
~0.5–0.7**; the measured 0.94 is the optimistic end of that range.

## 5. Stress tests (robustness.py)

| Test | Result | Verdict |
|---|---|---|
| Costs ×2 (0.2% fee + 0.1% slip) | Sharpe 1.14, +2311% | survives |
| Costs ×~4 (0.3% fee + 0.2% slip) | Sharpe 1.02, +1509% | survives — only ~11 trades/year, friction can't kill it |
| Execute 1 day late | Sharpe 1.04, +1677% | survives, but prompt execution is worth real money — the 24/7 bot matters |
| Execute 2 days late | Sharpe 1.01, +1426% | still no collapse |
| EMA200 alone (drop the RSI) | Sharpe 0.89, −65% DD | RSI filter **earns its place**: +0.34 Sharpe, −7pts DD |
| From 2018 (skip 2017 super-cycle) | 8b 1.06 vs hold 0.60 | edge is not a 2017 artifact |
| From 2020 | 8b 1.21 vs hold 0.85 | holds |
| From 2022 (recent regime only) | 8b 0.83 vs hold 0.36, DD −32% vs −67% | holds |

## 6. TradingView cross-check (independent implementation)

A previous run of `strategies/08b_trend_rsi_state.pine` on TradingView
(spot data, 2018–2026 with TradingView's own warm-up window) showed the
same qualitative result: strategy ~3× the return of hold with far smaller
drawdowns. Exact figures are not directly comparable to the tables above
because TradingView starts trading only after its 200-bar warm-up and uses
its own fill model — expect agreement in *shape and magnitude*, not to the
percentage point.

To re-run it: open BTCUSDT (Binance) · 1D · load the Pine script · Strategy
Tester → compare Net profit and Max drawdown against
`python3 backtest.py --start <TV's first trade date>`.

## Verdict — the foundations

| Foundation | Status |
|---|---|
| **Ticker** (BTCUSDT, Binance spot) | ✅ validated — deepest market, the data used everywhere |
| **Timeframe** (daily) | ✅ validated — 5m ruled out (costs), daily robust; 4h remains UNVALIDATED |
| **Strategy** (8b state rule, EMA200/RSI55) | ✅ robust — plateau, OOS positive, survives costs/delay, both ingredients justified |
| **Expectations** | ⚠️ honest ones only: forward Sharpe ~0.5–0.94, −30/−50% drawdowns WILL happen, holding will outearn it in pure bull years |

**Green light for the next phase**: dry-run → testnet → (weeks later, small
size) live. The remaining risk is not in the backtest — it is in execution
discipline, which is exactly what the bot removes.

*Note: numbers in this file supersede the slightly different figures quoted
in earlier docs (e.g. +3659%); those came from the original session's
engine. Same data, same story, small execution-model differences —
documented here from a clean re-run so everything is reproducible.*
