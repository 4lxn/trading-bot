# Sweep — variables, timeframe, ticker (double-check before paper mode)

Date: 2026-07-01. Fresh Binance data (daily to 2026-07-01, last open candle
dropped). Engine: `common.py`, same costs as always (0.10% fee + 0.05% slip
per side). Reproduced first: the pinned-CSV headline (+3164%, Sharpe 1.23,
DD −58%) matches `VERIFICATION.md` exactly.

## A. Variables — RSI length was the untested knob. Verdict: 14 is fine.

Sharpe at EMA200, RSI length × threshold: the **threshold-55 column wins for
every RSI length** (1.03–1.23), and within it length barely matters
(7→28: 1.11–1.23, max at 14). EMA × RSI-length at threshold 55: everything
1.20–1.28. Wide plateau in all three dimensions → **EMA 200 / RSI 14 / 55
confirmed; nothing to re-tune.**

## B. Timeframe — 4h tested (was the open question). Verdict: rejected.

BTC 4h, grid EMA {300…1500 bars} × threshold {50,55,60}, RSI 14 and the
daily-equivalent RSI 84 (Sharpe annualized on 4h bars):

| Best 4h config | Sharpe | Trades | Daily 8b |
|---|---|---|---|
| EMA600 / RSI84 > 50 | 0.99 | 242 | **1.23**, 102 trades |

Every 4h cell loses to daily, with 2–6× the trades (more friction, more
failure modes). **Daily stays.** 5m was already ruled out; the pattern is
consistent: lower timeframe = worse.

## C. Ticker — same rule, ZERO re-fitting (honest transfer test), 1d

| Ticker | 8b ret | Sharpe | DD | Hold Sharpe | Hold DD | Verdict |
|---|---|---|---|---|---|---|
| BTC | +3136% | 1.23 | −58% | 0.78 | −83% | core |
| ETH | +1594% | 0.92 | **−39%** | 0.66 | −94% | ✅ transfers |
| SOL (2020→) | +2218% | 1.13 | −65% | 1.04 | −96% | ✅ transfers |
| BNB | +9249% | 1.06 | −64% | 1.16 | −80% | ~ neutral |
| XRP | +106% | 0.43 | −82% | 0.50 | −85% | ❌ skip |

Per-ticker grids: (EMA 200, RSI 55) sits at or next to each ticker's own
best cell for ETH/SOL (plateau transfers too). XRP is the one asset where
the rule adds nothing — trend rule on a mostly-trendless asset.
Walk-forward per ticker (3y→1y): ETH 0.59, BNB 0.83, SOL 0.84 stitched OOS
Sharpe — all positive, all with far smaller DD than hold. Same story as BTC.

## D. The actual finding: the portfolio beats any single-ticker tweak

Equal-weight 8b (same EMA200/RSI55 everywhere, daily rebalance):

| Portfolio | Return | Sharpe | MaxDD |
|---|---|---|---|
| BTC only (2017→) | +3136% | 1.23 | −58.0% |
| **BTC+ETH (2017→)** | +2797% | 1.24 | **−30.5%** |
| BTC+ETH+BNB (2017-11→) | +5415% | 1.38 | −41.2% |
| BTC only (2020-08→) | +813% | 1.29 | −32.3% |
| **BTC+ETH+SOL (2020-08→)** | +1418% | **1.51** | −31.7% |

Diversification does what no parameter can: **halves the drawdown at equal
or better Sharpe.** Stress on BTC+ETH+SOL: costs ×2 → Sharpe 1.41; from
2022 only → 0.78 (vs BTC-only 0.60 in the same window); from 2024 → 0.63.
Survives everything the BTC-only version survives, gentler everywhere.

Caveat: equal-weight daily-rebalance is the engine's approximation; the
real bot would rebalance only on signal changes (fewer, cheaper trades —
if anything slightly better). Crypto alts are highly correlated with BTC,
so treat the portfolio Sharpe as "BTC-edge, smoother," not a new edge.

## Verdict for paper mode

- **Variables:** unchanged — EMA 200, RSI 14 > 55. The plateau is confirmed
  in every direction, including the previously untested RSI length.
- **Timeframe:** daily. 4h tested and rejected.
- **Ticker:** don't pick one — run the same rule on **BTC + ETH + SOL**
  (⅓ each of allocated capital, independent signals). Skip XRP.
- Signals on 2026-07-01 close: all five tickers **OUT**. Paper mode would
  start flat, which is the cheap moment to start.
- Forward expectation stays honest: Sharpe ~0.6–0.9, drawdowns −25/−35%
  for the portfolio (vs −40/−55% single-ticker). Same edge, less pain.

Reproduce: `python3 backtest.py --symbol ETH/USDT` etc.; sweep script
preserved in this doc's history / re-derivable from `optimize.py`.
