"""Ticker search and company name lookup using Yahoo Finance."""

import logging
import sqlite3
from pathlib import Path

import requests

from . import models

logger = logging.getLogger(__name__)

# Local cache table for ticker -> company name (avoids repeated API calls)
_CACHE = {}


def _ensure_names_table():
    """Create ticker_names cache table if it doesn't exist."""
    with models.get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticker_names (
                ticker TEXT PRIMARY KEY,
                company_name TEXT NOT NULL
            )
        """)


def search_tickers(query, max_results=8):
    """Search Yahoo Finance for tickers matching a query.

    Works with partial company names, ticker symbols, or ISINs.
    Returns list of {"symbol": str, "name": str, "exchange": str}
    """
    if not query or len(query) < 2:
        return []

    try:
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        r = requests.get(
            url,
            params={"q": query, "quotesCount": max_results, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()

        results = []
        for q in data.get("quotes", []):
            results.append({
                "symbol": q.get("symbol", ""),
                "name": q.get("shortname", q.get("longname", "")),
                "exchange": q.get("exchange", ""),
            })
        return results
    except Exception as e:
        logger.warning(f"Ticker search failed: {e}")
        return []


def get_company_name(ticker):
    """Get company name for a ticker. Uses local cache, falls back to Yahoo Finance."""
    # Check memory cache
    if ticker in _CACHE:
        return _CACHE[ticker]

    # Check DB cache
    _ensure_names_table()
    with models.get_conn() as conn:
        row = conn.execute(
            "SELECT company_name FROM ticker_names WHERE ticker=?", (ticker,)
        ).fetchone()
        if row:
            _CACHE[ticker] = row["company_name"]
            return row["company_name"]

    # Fetch from Yahoo Finance
    try:
        results = search_tickers(ticker, max_results=1)
        if results and results[0]["symbol"] == ticker:
            name = results[0]["name"]
        else:
            # Try direct info lookup
            import yfinance as yf
            info = yf.Ticker(ticker).fast_info
            name = getattr(info, "short_name", None) or ticker
    except Exception:
        name = ticker

    # Cache it
    _CACHE[ticker] = name
    with models.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ticker_names (ticker, company_name) VALUES (?, ?)",
            (ticker, name),
        )

    return name


def get_company_names(tickers):
    """Bulk lookup company names. Returns dict of {ticker: name}."""
    result = {}
    missing = []

    # Check caches first
    _ensure_names_table()
    for t in tickers:
        if t in _CACHE:
            result[t] = _CACHE[t]
        else:
            missing.append(t)

    if missing:
        with models.get_conn() as conn:
            placeholders = ",".join("?" for _ in missing)
            rows = conn.execute(
                f"SELECT ticker, company_name FROM ticker_names WHERE ticker IN ({placeholders})",
                missing,
            ).fetchall()
            for r in rows:
                result[r["ticker"]] = r["company_name"]
                _CACHE[r["ticker"]] = r["company_name"]
                missing.remove(r["ticker"])

    # Fetch remaining from Yahoo
    for t in missing:
        name = get_company_name(t)
        result[t] = name

    return result
