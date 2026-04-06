"""Fetch OHLCV data from yfinance (and optionally IBKR) with DB caching."""

import logging
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from pathlib import Path

# Fix yfinance TzCache folder issue in containers
_cache_dir = os.environ.get("PORTFOLIO_DATA_DIR", "/data") + "/.yf_cache"
os.makedirs(_cache_dir, exist_ok=True)
yf.set_tz_cache_location(_cache_dir)

from . import models

logger = logging.getLogger(__name__)

# Period string -> number of calendar days
_PERIOD_DAYS = {
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "1Y": 365,
    "2Y": 730,
    "5Y": 1825,
}

# Period string -> yfinance period argument
_YF_PERIOD = {
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "2Y": "2y",
    "5Y": "5y",
}


def fetch_ohlcv_yfinance(ticker, period="1y", interval="1d"):
    """Download OHLCV data from yfinance for a single ticker.

    Returns
    -------
    pd.DataFrame
        Columns: date, open, high, low, close, volume (lowercase).
        Empty DataFrame on failure.
    """
    try:
        raw = yf.download(ticker, period=period, interval=interval, timeout=30)
    except Exception as e:
        logger.error(f"yfinance OHLCV download failed for {ticker}: {e}")
        return pd.DataFrame()

    if raw.empty:
        logger.warning(f"No OHLCV data returned for {ticker}")
        return pd.DataFrame()

    # yfinance returns multi-level columns for single ticker too (newer versions)
    # Flatten if needed
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df["date"] = df.index
    if hasattr(df["date"].iloc[0], "strftime"):
        df["date"] = df["date"].apply(lambda x: x.strftime("%Y-%m-%d"))
    else:
        df["date"] = df["date"].astype(str).str[:10]

    df = df.reset_index(drop=True)
    df = df[["date", "open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["open", "close"])

    return df


def fetch_and_store_ohlcv(ticker, period="2y", source="yfinance"):
    """Fetch OHLCV from yfinance and store in the database.

    Returns the fetched DataFrame.
    """
    yf_period = _YF_PERIOD.get(period.upper(), period)
    df = fetch_ohlcv_yfinance(ticker, period=yf_period)

    if df.empty:
        return df

    currency = "GBX" if ticker.endswith(".L") else "USD"

    records = [
        (ticker, row["date"], row["open"], row["high"], row["low"],
         row["close"], int(row["volume"]) if pd.notna(row["volume"]) else 0,
         currency, source)
        for _, row in df.iterrows()
    ]

    models.insert_ohlcv(records)
    logger.info(f"Stored {len(records)} OHLCV bars for {ticker}")

    return df


def get_ohlcv_df(ticker, period="1Y", ibkr_client=None):
    """Main entry point — get OHLCV DataFrame, fetching if necessary.

    Checks the DB cache first.  If data is missing or stale (last bar
    older than 2 calendar days for daily data), fetches fresh data.

    Parameters
    ----------
    ticker : str
    period : str
        One of '1M', '3M', '6M', '1Y', '2Y', '5Y'.
    ibkr_client : optional
        If provided and connected, use IBKR for data. Falls back to yfinance.

    Returns
    -------
    pd.DataFrame
        Columns: date, open, high, low, close, volume (lowercase).
    """
    period = period.upper()
    days = _PERIOD_DAYS.get(period, 365)
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Check cache freshness
    last_date = models.get_last_ohlcv_date(ticker)
    stale = True
    if last_date:
        days_old = (datetime.utcnow() - datetime.strptime(last_date, "%Y-%m-%d")).days
        stale = days_old > 2  # Allow weekend gap

    if stale:
        # Try IBKR first if available
        fetched = False
        if ibkr_client is not None:
            try:
                if hasattr(ibkr_client, "is_connected") and ibkr_client.is_connected():
                    df = ibkr_client.get_historical_ohlcv(ticker, period=period)
                    if df is not None and not df.empty:
                        currency = "GBX" if ticker.endswith(".L") else "USD"
                        records = [
                            (ticker, row["date"], row["open"], row["high"], row["low"],
                             row["close"], int(row["volume"]) if pd.notna(row["volume"]) else 0,
                             currency, "ibkr")
                            for _, row in df.iterrows()
                        ]
                        models.insert_ohlcv(records)
                        fetched = True
                        logger.info(f"Fetched {len(records)} OHLCV bars from IBKR for {ticker}")
            except Exception as e:
                logger.warning(f"IBKR fetch failed for {ticker}, falling back to yfinance: {e}")

        if not fetched:
            fetch_and_store_ohlcv(ticker, period=period, source="yfinance")

    # Read from DB
    rows = models.get_ohlcv(ticker, start_date=start_date)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Ensure numeric types
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

    return df
