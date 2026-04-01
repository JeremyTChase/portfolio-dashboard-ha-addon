"""Fetch prices from yfinance and update the database."""

import logging
from datetime import datetime, timedelta

import os
import pandas as pd
import yaml
import yfinance as yf
from pathlib import Path

# Fix yfinance TzCache folder issue in containers
_cache_dir = os.environ.get("PORTFOLIO_DATA_DIR", "/data") + "/.yf_cache"
os.makedirs(_cache_dir, exist_ok=True)
yf.set_tz_cache_location(_cache_dir)

from . import models

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent

def _load_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        return yaml.safe_load(f)


def fetch_and_store_prices():
    """Fetch missing prices for all portfolio tickers and macro indicators."""
    cfg = _load_config()
    tickers = models.get_all_tickers()
    macro_tickers = cfg.get("macro_tickers", [])
    all_tickers = list(set(tickers + macro_tickers))

    if not all_tickers:
        logger.info("No tickers to update")
        return

    # Find the earliest missing date across all tickers
    start_date = None
    for t in all_tickers:
        last = models.get_last_price_date(t)
        if last is None:
            # No data at all — fetch 2 years
            candidate = (datetime.utcnow() - timedelta(days=730)).strftime("%Y-%m-%d")
        else:
            candidate = (datetime.strptime(last, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        if start_date is None or candidate < start_date:
            start_date = candidate

    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    if start_date >= end_date:
        logger.info("All prices up to date")
        return

    logger.info(f"Fetching prices for {len(all_tickers)} tickers from {start_date} to {end_date}")

    try:
        raw = yf.download(all_tickers, start=start_date, end=end_date, timeout=60)
    except Exception as e:
        logger.error(f"yfinance download failed: {e}")
        return

    if raw.empty:
        logger.warning("No data returned from yfinance")
        return

    # Handle single vs multi-ticker response
    if len(all_tickers) == 1:
        close = raw[["Close"]].rename(columns={"Close": all_tickers[0]})
    else:
        close = raw["Close"]

    # Forward-fill for mixed UK/US market calendars
    close = close.ffill()

    # Store portfolio ticker prices
    price_records = []
    macro_records = []

    for col in close.columns:
        series = close[col].dropna()
        for date_idx, val in series.items():
            date_str = date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, "strftime") else str(date_idx)[:10]
            currency = "GBX" if str(col).endswith(".L") else "USD"
            if col in macro_tickers:
                macro_records.append((str(col), date_str, float(val)))
            else:
                price_records.append((str(col), date_str, float(val), currency))

    if price_records:
        models.insert_prices(price_records)
        logger.info(f"Inserted {len(price_records)} price records")

    if macro_records:
        models.insert_macro(macro_records)
        logger.info(f"Inserted {len(macro_records)} macro records")


def is_market_hours():
    """Check if current UTC hour is within market hours."""
    cfg = _load_config()
    hours = cfg["price_update"]["market_hours_utc"]
    current_hour = datetime.utcnow().hour
    return hours["start"] <= current_hour <= hours["end"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    models.init_db()
    fetch_and_store_prices()
