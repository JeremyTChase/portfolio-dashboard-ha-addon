"""Portfolio weight and P&L calculations."""

import logging

from . import models

logger = logging.getLogger(__name__)

# LSE tickers where yfinance reports prices in GBP (not GBp/pence)
# These should NOT be divided by 100
# Determined by checking yf.Ticker(t).fast_info.currency == "GBP"
_LSE_GBP_TICKERS = {"VJPN.L", "VWRP.L"}

# Cache for FX rate within a single calculation cycle
_fx_cache = {}


def _get_gbpusd_rate():
    """Get latest GBP/USD exchange rate from macro indicators."""
    if "gbpusd" not in _fx_cache:
        macro = models.get_latest_macro()
        if "GBPUSD=X" in macro:
            _fx_cache["gbpusd"] = macro["GBPUSD=X"]["value"]
        else:
            _fx_cache["gbpusd"] = 1.30
    return _fx_cache["gbpusd"]


def _price_to_gbp(ticker, price):
    """Convert a raw yfinance price to GBP.

    yfinance currency conventions:
    - Most .L tickers: GBp (pence) -> divide by 100
    - Some .L ETFs (VJPN, VWRP): GBP (pounds) -> use as-is
    - US tickers: USD -> convert using GBPUSD rate
    """
    if price is None or price == 0:
        return 0.0

    if ticker.endswith(".L"):
        if ticker in _LSE_GBP_TICKERS:
            # Already in GBP
            return price
        else:
            # GBp (pence) -> GBP
            return price / 100.0
    else:
        # USD -> GBP
        gbpusd = _get_gbpusd_rate()
        return price / gbpusd


def calculate_portfolio_summary(portfolio_id):
    """Calculate market values, weights, and P&L for a portfolio.

    All values returned in GBP.
    """
    positions = models.get_positions(portfolio_id)
    if not positions:
        return []

    # Clear FX cache for fresh rate
    _fx_cache.clear()

    rows = []
    for pos in positions:
        ticker = pos["ticker"]
        shares = pos["shares"]
        price_data = models.get_latest_price(ticker)
        raw_price = price_data["close"] if price_data else 0.0

        display_price = _price_to_gbp(ticker, raw_price)
        market_value = shares * display_price

        avg_cost = pos["avg_cost_basis"]
        pnl = None
        pnl_pct = None
        if avg_cost and avg_cost > 0:
            cost_value = shares * avg_cost
            pnl = market_value - cost_value
            pnl_pct = pnl / cost_value

        rows.append({
            "ticker": ticker,
            "shares": shares,
            "current_price": display_price,
            "market_value": market_value,
            "avg_cost": avg_cost,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "currency": "GBP",
        })

    total_value = sum(r["market_value"] for r in rows)
    for r in rows:
        r["weight"] = r["market_value"] / total_value if total_value > 0 else 0
    rows.sort(key=lambda x: x["weight"], reverse=True)

    return rows


def get_portfolio_total_value(portfolio_id):
    """Get total portfolio market value in GBP."""
    rows = calculate_portfolio_summary(portfolio_id)
    return sum(r["market_value"] for r in rows)
