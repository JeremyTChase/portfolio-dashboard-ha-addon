"""Parse Freetrade CSV activity feed exports and portfolios.json into positions."""

import csv
import json
from collections import defaultdict
from pathlib import Path

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
    # Already in YF format
    if "." in ft_ticker or ft_ticker.isupper():
        return ft_ticker
    return ft_ticker


def parse_freetrade_csv(filepath):
    """Parse Freetrade activity feed CSV and return net positions.

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
