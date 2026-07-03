# BTC Trading Bot — Strategy 8b

A trend-following strategy for BTC that aims to be **actually profitable**
(not just on paper), validated with real data and automated to run 24/7.

**The rule (strategy 8b):** be long while `close > EMA(200)` **and**
`RSI(14) > 55` on the **daily** close; otherwise sit in cash. BTC, spot,
long-only, no leverage.

| 2017–2026, 100% of capital | Strategy 8b | Buy & hold |
|---|---|---|
| Total return | **+3164%** | +1303% |
| Sharpe | **1.23** | 0.79 |
| Max drawdown | **−58%** | −83% |

*(Re-verified 2026-07-02 on an independent data export — see
`VERIFICATION.md` for the full evidence: parameter plateau, walk-forward,
cost/delay stress tests.)*

**The honest nuance:** the edge is concentrated in **losing little in the
bad years** (2018: −33% vs −73%; 2022: −8% vs −64%). In pure bull years
(2020, 2023, 2024) holding wins. It is **crash insurance with a modest
edge**, not a money machine. Realistic forward expectation (walk-forward):
**Sharpe ~0.5–0.9 with roughly half the drawdown of holding**. The
historical return is inflated by BTC's super-cycle; expect the protection,
not the magnitude.

**Current status (last close 2026-06-26):** the signal is **OUT** — BTC
~60k is below the EMA200 with RSI ~30. In cash, sitting out the decline.
Correct.

## How we got here

1. **Five simple strategies on 5m** (EMA, RSI, Bollinger, MACD, Stochastic):
   only EMA and MACD showed anything, and barely. **On 5m, costs eat the edge.**
2. **"Pro" versions on 5m** (filters + trailing stops): still not profitable.
3. **Research:** the only robustly documented edge is **trend following on
   high timeframes** (daily) — not scalping.
4. **ORB** (opening range breakout): built, unconvincing in backtest.
5. **Multi-indicator, long-only, 4h/1D** (strategies 7–10): nothing
   profitable in <1 year of data — but **<1 year is not a valid test**
   (tiny sample; the EMA200 alone needs 200 days to warm up).
6. **Serious Python backtest** with real data (Binance BTCUSDT daily
   2017–2026). This is where everything became clear.
7. **Walk-forward optimization:** robust result (wide plateau, not a spike).
   Best parameters: RSI threshold **55**, EMA **200**. → `OPTIMIZATION.md`
8. **Key finding:** strategy 8 *as originally written* (crossover entry +
   ATR trailing stop) did **NOT** beat buy & hold. What wins is the simple
   **state rule** — be long while `close > EMA200 and RSI(14) > 55`.
   → **8b was born.** → `BACKTEST_RESULTS.md`
9. **8b validated** over the full range (2017–2026). → `FULL_RANGE_RESULTS.md`
10. **Cross-checked on TradingView** (spot, 2018–2026): +2068% vs hold +603%,
    matching the Python engine (+2362% on that window). The code is faithful.

## Repository layout

| Path | What it is |
|---|---|
| `strategies/08b_trend_rsi_state.pine` | **The final strategy** (TradingView, with BUY/SELL alerts) |
| `strategies/01…10_*.pine` | Historical attempts, kept for reference (see verdict in each header) |
| `backtest.py` | Backtest engine — metrics, yearly table, `output/equity_curve.png` |
| `optimize.py` | Grid search + walk-forward — `output/heatmap_*.png` |
| `strategy8_replica.py` | Proof that original strategy 8 loses to hold; 8b wins |
| `robustness.py` + `VERIFICATION.md` | Stress tests + the full verification record |
| `data/btcusdt_1d_verified_20260626.csv` | Pinned dataset every number was verified on |
| `common.py` | Shared data/indicator/engine code |
| `bot_8b.py` + `BOT_README.md` | Execution bot (ccxt): dry-run/testnet/live, idempotent, Telegram |
| `run.sh` + `launchd/com.trading8b.bot.plist` | 24/7 deployment on the Mac mini |
| `paper_trading_8b.xlsx` | Paper-trading log with automatic P&L/drawdown |
| `BACKTEST_RESULTS.md`, `OPTIMIZATION.md`, `FULL_RANGE_RESULTS.md` | Validation records |
| `SWEEP_RESULTS.md` | 2026-07-01 double-check: RSI length, 4h (rejected), tickers → **BTC+ETH+SOL portfolio** |

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
source .venv/bin/activate

python3 backtest.py            # downloads data, prints metrics + current signal
python3 optimize.py            # heatmaps + walk-forward
python3 strategy8_replica.py   # strategy 8 vs 8b vs hold
python3 robustness.py          # cost/delay/sub-window stress tests

cp .env.example .env           # configure the bot (keys, sizing, Telegram)
./run.sh                       # one bot cycle (dry-run by default)
```

To deploy on the Mac mini 24/7, follow `BOT_README.md`. The path is
**dry-run → testnet → live**, weeks at each step, keys **without withdrawal
permission**, starting with a small `MAX_USDT`.

## Open questions / decisions

1. **Sizing:** 100% of capital when long (= the backtest) or more
   conservative? The bot exposes `ORDER_FRAC` + `MAX_USDT` — define your risk.
2. **Spot vs futures:** currently spot, long-only, **no liquidation risk**.
   1x futures could be considered but nothing gets leveraged without re-validating.
3. **Portfolio or ensemble?** ✅ ANSWERED (2026-07-01, `SWEEP_RESULTS.md`):
   8b transfers to ETH and SOL with zero re-fitting; the BTC+ETH+SOL
   equal-weight portfolio halves the drawdown at equal-or-better Sharpe.
   XRP does not work. Ensemble (8b + MACD + Donchian) still open.
4. **4h timeframe?** ✅ ANSWERED (2026-07-01, `SWEEP_RESULTS.md`): tested
   with the same rigor — every 4h config loses to daily with 2–6× the
   trades. Rejected; daily stays.
5. **Execution frequency:** hourly (idempotent, robust to sleep — the current
   default) vs exactly at the 00:00 UTC close (less slippage).
6. **Operational robustness:** restarts, exchange outages, double runs — the
   bot re-reads the real position every cycle (idempotent), but keep
   monitoring and reviewing logs.

## Honest ways to improve returns

**Improve RISK-ADJUSTED returns (the good ones):**

1. **Diversify across liquid coins** (BTC, ETH, SOL…) with the same rule —
   trend following is fundamentally a *portfolio* strategy; smooths drawdowns,
   usually raises Sharpe.
2. **Ensemble of strategies** (8b + MACD + Donchian) — spreads risk across
   different logics.
3. **Volatility-targeted sizing** (position ∝ 1/ATR) — keeps risk stable over
   time; institutional technique that tends to improve Sharpe.
4. **Minimize costs:** limit/maker orders, low-fee exchange, execute near the
   close — less friction = more net edge.
5. **Reliable 24/7 execution** — never miss a signal, remove emotion. This
   alone is "maximizing" in practice.

**Raise GROSS returns but also risk (careful):**

6. **More size / moderate leverage:** scales *everything*, including the
   −30/−50% drawdowns and liquidation risk. Only with eyes wide open, never
   suddenly, never without re-validating.

**The honest ceiling:** the edge is modest (forward Sharpe ~0.7). Truly
maximizing = **don't sabotage it** (discipline/automation) + **diversify** +
**size to your tolerance** + **keep costs low**. There is no lever that adds
return without adding risk; anyone selling one is lying.

## Honest reminders

- Backtest ≠ live: there will be slippage, and **−30% to −50% drawdowns WILL
  happen**.
- The historical return is inflated by BTC's bull cycle; expect the edge
  (protection), not the magnitude.
- Start on **testnet**, then minimal real size, with API keys **without
  withdrawal permission**.
- This is educational material, **not financial advice**. The decisions and
  the risk are yours.
