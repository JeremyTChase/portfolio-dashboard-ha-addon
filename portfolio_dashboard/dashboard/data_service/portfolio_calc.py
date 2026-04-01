"""Portfolio weight and P&L calculations."""

from . import models

# Tickers that trade on LSE in USD (not GBX) despite having .L suffix
_LSE_USD_TICKERS = {"VJPN.L", "VWRP.L", "IUSA.L"}


def _get_gbpusd_rate():
    """Get latest GBP/USD exchange rate from macro indicators."""
    macro = models.get_latest_macro()
    if "GBPUSD=X" in macro:
        return macro["GBPUSD=X"]["value"]
    return 1.30  # fallback


def _price_to_gbp(ticker, price):
    """Convert a raw yfinance price to GBP.

    - .L tickers: price is in GBX (pence) -> divide by 100 for GBP
    - .L tickers in USD list (VJPN, VWRP, IUSA): price is in USD -> convert
    - US tickers: price is in USD -> convert to GBP
    """
    if ticker in _LSE_USD_TICKERS:
        # These LSE ETFs are priced in USD on yfinance
        gbpusd = _get_gbpusd_rate()
        return price / gbpusd
    elif ticker.endswith(".L"):
        # Standard UK stocks priced in GBX (pence)
        return price / 100.0
    else:
        # US stocks priced in USD
        gbpusd = _get_gbpusd_rate()
        return price / gbpusd


def calculate_portfolio_summary(portfolio_id):
    """Calculate market values, weights, and P&L for a portfolio.

    All values returned in GBP.

    Returns list of dicts with: ticker, shares, current_price, market_value,
    weight, cost_basis, pnl, pnl_pct, currency.
    """
    positions = models.get_positions(portfolio_id)
    if not positions:
        return []

    rows = []
    for pos in positions:
        ticker = pos["ticker"]
        shares = pos["shares"]
        price_data = models.get_latest_price(ticker)
        raw_price = price_data["close"] if price_data else 0.0

        # Convert to GBP
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

    # Calculate weights
    total_value = sum(r["market_value"] for r in rows)
    for r in rows:
        r["weight"] = r["market_value"] / total_value if total_value > 0 else 0
    rows.sort(key=lambda x: x["weight"], reverse=True)

    return rows


def get_portfolio_total_value(portfolio_id):
    """Get total portfolio market value in GBP."""
    rows = calculate_portfolio_summary(portfolio_id)
    return sum(r["market_value"] for r in rows)
