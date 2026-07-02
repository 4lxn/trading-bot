"""Shared utilities: data loading, indicators, backtest engine, metrics.

Used by backtest.py, optimize.py, strategy8_replica.py and bot_8b.py.

Engine assumptions (kept deliberately conservative and simple):
- Signals are evaluated on the daily close.
- Positions are applied from the NEXT bar (no look-ahead).
- Returns are close-to-close while in position.
- Fees + slippage are charged on every position change (entry and exit).
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

DEFAULT_SYMBOL = "BTC/USDT"
DEFAULT_TIMEFRAME = "1d"
DEFAULT_START = "2017-08-17"  # first day of BTCUSDT on Binance

# Round-trip friction per side: 0.10% taker fee + 0.05% slippage.
DEFAULT_FEE = 0.001
DEFAULT_SLIPPAGE = 0.0005

TRADING_DAYS_PER_YEAR = 365  # crypto trades every day


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def csv_path(symbol: str = DEFAULT_SYMBOL, timeframe: str = DEFAULT_TIMEFRAME) -> str:
    name = symbol.replace("/", "").lower()
    return os.path.join(DATA_DIR, f"{name}_{timeframe}.csv")


def download_ohlcv(symbol: str = DEFAULT_SYMBOL, timeframe: str = DEFAULT_TIMEFRAME,
                   start: str = DEFAULT_START) -> pd.DataFrame:
    """Download full OHLCV history from Binance via ccxt (paginated)."""
    import ccxt  # imported lazily so offline tools work without it

    exchange = ccxt.binance({"enableRateLimit": True})
    since = exchange.parse8601(f"{start}T00:00:00Z")
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
        time.sleep(exchange.rateLimit / 1000)
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").set_index("date").drop(columns="timestamp")
    return df.astype(float)


def load_data(csv: str | None = None, symbol: str = DEFAULT_SYMBOL,
              timeframe: str = DEFAULT_TIMEFRAME, start: str = DEFAULT_START,
              refresh: bool = False) -> pd.DataFrame:
    """Load OHLCV from CSV, downloading (and caching) it if missing."""
    path = csv or csv_path(symbol, timeframe)
    if refresh or not os.path.exists(path):
        print(f"Downloading {symbol} {timeframe} from Binance...")
        df = download_ohlcv(symbol, timeframe, start)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df.to_csv(path)
        print(f"Saved {len(df)} candles to {path}")
        return df
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    return df.astype(float)


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI (matches TradingView's ta.rsi)."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Wilder's ATR (matches TradingView's ta.atr)."""
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


# ---------------------------------------------------------------------------
# Strategy 8b: state rule
# ---------------------------------------------------------------------------

def state_signal(df: pd.DataFrame, ema_len: int = 200, rsi_len: int = 14,
                 rsi_threshold: float = 55) -> pd.Series:
    """Strategy 8b: be long while close > EMA(ema_len) AND RSI(rsi_len) > threshold.

    Returns a boolean Series evaluated on each daily close.
    """
    return (df["close"] > ema(df["close"], ema_len)) & (rsi(df["close"], rsi_len) > rsi_threshold)


def run_backtest(df: pd.DataFrame, signal: pd.Series,
                 fee: float = DEFAULT_FEE, slippage: float = DEFAULT_SLIPPAGE) -> pd.DataFrame:
    """Turn a boolean signal into an equity curve.

    The signal computed on bar t's close takes effect on bar t+1.
    """
    out = df.copy()
    out["signal"] = signal.astype(bool)
    out["position"] = out["signal"].shift(1).fillna(False).astype(float)
    daily_ret = out["close"].pct_change().fillna(0.0)
    cost = (fee + slippage) * out["position"].diff().abs().fillna(0.0)
    out["strategy_ret"] = out["position"] * daily_ret - cost
    out["equity"] = (1 + out["strategy_ret"]).cumprod()
    out["hold_equity"] = (1 + daily_ret).cumprod()
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def max_drawdown(equity: pd.Series) -> float:
    return (equity / equity.cummax() - 1).min()


def sharpe(returns: pd.Series) -> float:
    if returns.std() == 0:
        return 0.0
    return returns.mean() / returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def cagr(equity: pd.Series) -> float:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return equity.iloc[-1] ** (1 / years) - 1


def trade_stats(result: pd.DataFrame) -> tuple[int, float]:
    """Number of round-trip trades and win rate, from the position column."""
    pos = result["position"]
    entries = ((pos == 1) & (pos.shift(1) == 0))
    trades = []
    entry_equity = None
    for i in range(len(result)):
        if entries.iloc[i]:
            entry_equity = result["equity"].iloc[i - 1] if i > 0 else 1.0
        elif entry_equity is not None and pos.iloc[i] == 0 and pos.iloc[i - 1] == 1:
            trades.append(result["equity"].iloc[i] / entry_equity - 1)
            entry_equity = None
    if entry_equity is not None:  # trade still open at end of data
        trades.append(result["equity"].iloc[-1] / entry_equity - 1)
    if not trades:
        return 0, 0.0
    wins = sum(1 for t in trades if t > 0)
    return len(trades), wins / len(trades)


def summarize(result: pd.DataFrame, label: str = "strategy") -> dict:
    eq = result["equity"]
    n_trades, win_rate = trade_stats(result)
    return {
        "label": label,
        "total_return": eq.iloc[-1] - 1,
        "cagr": cagr(eq),
        "sharpe": sharpe(result["strategy_ret"]),
        "max_drawdown": max_drawdown(eq),
        "exposure": result["position"].mean(),
        "trades": n_trades,
        "win_rate": win_rate,
    }


def summarize_hold(result: pd.DataFrame) -> dict:
    eq = result["hold_equity"]
    return {
        "label": "buy & hold",
        "total_return": eq.iloc[-1] - 1,
        "cagr": cagr(eq),
        "sharpe": sharpe(eq.pct_change().fillna(0.0)),
        "max_drawdown": max_drawdown(eq),
        "exposure": 1.0,
        "trades": 1,
        "win_rate": float("nan"),
    }


def print_summary(stats: dict) -> None:
    print(f"  {stats['label']}:")
    print(f"    Total return : {stats['total_return']:+.1%}")
    print(f"    CAGR         : {stats['cagr']:+.1%}")
    print(f"    Sharpe       : {stats['sharpe']:.2f}")
    print(f"    Max drawdown : {stats['max_drawdown']:.1%}")
    print(f"    Exposure     : {stats['exposure']:.1%}")
    print(f"    Trades       : {stats['trades']}  (win rate {stats['win_rate']:.0%})"
          if stats["trades"] and not np.isnan(stats.get("win_rate", np.nan))
          else f"    Trades       : {stats['trades']}")


def yearly_table(result: pd.DataFrame) -> pd.DataFrame:
    """Year-by-year strategy vs hold returns."""
    def yearly(returns: pd.Series) -> pd.Series:
        return (1 + returns).groupby(returns.index.year).prod() - 1

    table = pd.DataFrame({
        "strategy": yearly(result["strategy_ret"]),
        "hold": yearly(result["hold_equity"].pct_change().fillna(0.0)),
    })
    table["beats_hold"] = table["strategy"] > table["hold"]
    return table
