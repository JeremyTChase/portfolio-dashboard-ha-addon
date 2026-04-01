"""Portfolio weight and P&L calculations."""

from . import models


def calculate_portfolio_summary(portfolio_id):
    """Calculate market values, weights, and P&L for a portfolio.

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
        current_price = price_data["close"] if price_data else 0.0

        # GBX -> GBP conversion for display
        display_price = current_price
        if ticker.endswith(".L"):
            display_price = current_price / 100.0  # GBX to GBP

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
            "currency": pos["currency"],
        })

    # Calculate weights
    total_value = sum(r["market_value"] for r in rows)
    for r in rows:
        r["weight"] = r["market_value"] / total_value if total_value > 0 else 0
    # Sort by weight descending
    rows.sort(key=lambda x: x["weight"], reverse=True)

    return rows


def get_portfolio_total_value(portfolio_id):
    """Get total portfolio market value in display currency."""
    rows = calculate_portfolio_summary(portfolio_id)
    return sum(r["market_value"] for r in rows)
