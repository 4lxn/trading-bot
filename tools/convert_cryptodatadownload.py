#!/usr/bin/env python3
"""Convert a CryptoDataDownload.com daily CSV (e.g. Binance_BTCUSDT_d.csv)
into the OHLCV format used by this repo's engine (data/btcusdt_1d.csv).

CryptoDataDownload files have a URL banner on line 1, columns
Unix,Date,Symbol,Open,High,Low,Close,Volume BTC,Volume USDT,tradecount
and rows in reverse chronological order.

Usage:
    python3 tools/convert_cryptodatadownload.py Binance_BTCUSDT_d.csv [output.csv]
"""

import os
import sys

import pandas as pd


def convert(src: str, dst: str) -> pd.DataFrame:
    df = pd.read_csv(src, skiprows=1)
    df.columns = [c.strip().lower() for c in df.columns]
    base_volume = next(c for c in df.columns if c.startswith("volume"))
    out = pd.DataFrame({
        "date": pd.to_datetime(df["date"], utc=True),
        "open": df["open"],
        "high": df["high"],
        "low": df["low"],
        "close": df["close"],
        "volume": df[base_volume],
    }).set_index("date").sort_index()
    # guard against gaps/duplicates in the source file
    out = out[~out.index.duplicated(keep="last")]
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    out.to_csv(dst)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(repo, "data", "btcusdt_1d.csv")
    df = convert(src, dst)
    print(f"Wrote {dst}: {len(df)} candles, {df.index[0].date()} -> {df.index[-1].date()}")
