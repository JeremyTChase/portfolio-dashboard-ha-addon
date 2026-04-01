"""Parse Freetrade CSV activity feed exports and portfolios.json into positions."""

import csv
import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Freetrade ticker -> Yahoo Finance ticker mapping
TICKER_MAP = {
    "AAL": "AAL.L", "ASMLa": "ASML", "BAB": "BAB.L", "BARC": "BARC.L",
    "BP.": "BP.L", "CURY": "CURY.L", "DGE": "DGE.L", "DNN": "DNN",
    "DELL": "DELL", "GSK": "GSK.L", "HIMS": "HIMS", "HSBA": "HSBA.L",
    "INTC": "INTC", "ISF": "ISF.L", "IUSA": "IUSA.L", "LSEG": "LSEG.L",
    "MU": "MU", "NVDA": "NVDA", "NVO": "NVO", "PLTR": "PLTR",
    "PSN": "PSN.L", "RNWH": "RNWH.L", "RR.": "RR.L",
    "SJPA": "SJPA.L", "TSLA": "TSLA", "VJPN": "VJPN.L", "VWRP": "VWRP.L",
}


def map_ticker(ft_ticker):
    """Map a Freetrade ticker to Yahoo Finance ticker."""
    if ft_ticker in TICKER_MAP:
        return TICKER_MAP[ft_ticker]
    if "." in ft_ticker or ft_ticker.isupper():
        return ft_ticker
    return ft_ticker


def parse_freetrade_csv(filepath):
    """Parse Freetrade activity feed CSV and return net positions.

    WARNING: This calculates positions from scratch using only the trades in the CSV.
    If the CSV only covers a partial window (e.g. 3 months), positions bought earlier
    will be missing. Use parse_freetrade_csv_delta() instead for partial exports.

    Returns dict of {yf_ticker: {"shares": float, "avg_cost": float|None, "currency": str}}
    """
    holdings = defaultdict(lambda: {"buys": 0.0, "sells": 0.0, "total_cost": 0.0, "buy_qty": 0.0})

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Type") != "ORDER" or not row.get("Ticker"):
                continue

            ft_ticker = row["Ticker"]
            yf_ticker = map_ticker(ft_ticker)
            qty = float(row["Quantity"]) if row.get("Quantity") else 0
            price = float(row["Price per Share in Account Currency"]) if row.get("Price per Share in Account Currency") else 0

            if row["Buy / Sell"] == "BUY":
                holdings[yf_ticker]["buys"] += qty
                holdings[yf_ticker]["total_cost"] += qty * price
                holdings[yf_ticker]["buy_qty"] += qty
            elif row["Buy / Sell"] == "SELL":
                holdings[yf_ticker]["sells"] += qty

    result = {}
    for ticker, data in holdings.items():
        net_shares = data["buys"] - data["sells"]
        if net_shares > 0.001:
            avg_cost = data["total_cost"] / data["buy_qty"] if data["buy_qty"] > 0 else None
            result[ticker] = {
                "shares": round(net_shares, 4),
                "avg_cost": round(avg_cost, 4) if avg_cost else None,
                "currency": "GBP",
            }
    return result


def parse_freetrade_csv_delta(filepath, since_date):
    """Parse only trades AFTER since_date from a Freetrade CSV.

    Use this for partial exports (3/6/12 month). It extracts individual
    trades newer than since_date so they can be applied as deltas to
    existing positions.

    Args:
        filepath: path to the Freetrade CSV
        since_date: ISO date string (YYYY-MM-DD) — only trades after this date are returned

    Returns:
        list of dicts: [{"ticker": str, "action": "BUY"|"SELL", "shares": float,
                         "price": float, "date": str, "currency": str}]
    """
    trades = []
    cutoff = datetime.fromisoformat(since_date)

    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Type") != "ORDER" or not row.get("Ticker"):
                continue

            # Parse trade timestamp
            ts = row.get("Timestamp", "")
            try:
                trade_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            # Skip trades on or before the cutoff
            if trade_dt.replace(tzinfo=None) <= cutoff:
                continue

            ft_ticker = row["Ticker"]
            yf_ticker = map_ticker(ft_ticker)
            qty = float(row["Quantity"]) if row.get("Quantity") else 0
            price = float(row["Price per Share in Account Currency"]) if row.get("Price per Share in Account Currency") else 0
            action = row["Buy / Sell"]

            if action in ("BUY", "SELL") and qty > 0:
                trades.append({
                    "ticker": yf_ticker,
                    "action": action,
                    "shares": round(qty, 4),
                    "price": round(price, 4),
                    "date": trade_dt.strftime("%Y-%m-%d %H:%M"),
                    "currency": "GBP",
                })
                logger.info(f"  New trade: {action} {qty:.4f} {yf_ticker} @ {price:.2f} on {trade_dt.strftime('%Y-%m-%d')}")

    logger.info(f"Found {len(trades)} new trades after {since_date}")
    return trades


def apply_trades_to_positions(existing_positions, trades):
    """Apply a list of trades as deltas to existing positions.

    Args:
        existing_positions: list of sqlite Row objects with 'ticker' and 'shares'
        trades: list from parse_freetrade_csv_delta()

    Returns:
        dict of {ticker: {"shares": float, "avg_cost": None, "currency": str}}
        representing the updated positions
    """
    # Build current state from existing positions
    current = {}
    for p in existing_positions:
        current[p["ticker"]] = {
            "shares": p["shares"],
            "avg_cost": p.get("avg_cost_basis"),
            "currency": p.get("currency", "GBP"),
        }

    # Apply each trade
    for trade in trades:
        ticker = trade["ticker"]
        qty = trade["shares"]

        if ticker not in current:
            current[ticker] = {"shares": 0.0, "avg_cost": None, "currency": trade["currency"]}

        if trade["action"] == "BUY":
            current[ticker]["shares"] += qty
        elif trade["action"] == "SELL":
            current[ticker]["shares"] -= qty

    # Remove positions that went to zero or negative
    result = {}
    for ticker, data in current.items():
        if data["shares"] > 0.001:
            data["shares"] = round(data["shares"], 4)
            result[ticker] = data
        else:
            logger.info(f"  Position closed: {ticker}")

    return result


def parse_portfolios_json(filepath):
    """Parse the existing portfolios.json format.

    Returns dict of {portfolio_id: {yf_ticker: {"shares": float, ...}}}
    """
    with open(filepath) as f:
        data = json.load(f)

    result = {}
    for portfolio_id, pdata in data.items():
        positions = {}
        for ticker, shares in pdata["holdings"].items():
            positions[ticker] = {
                "shares": shares,
                "avg_cost": None,
                "currency": "GBX" if ticker.endswith(".L") else "USD",
            }
        result[portfolio_id] = {"name": pdata["name"], "positions": positions}
    return result
