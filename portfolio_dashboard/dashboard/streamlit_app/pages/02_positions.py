"""Positions page — detailed P&L table."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()
import pandas as pd
from data_service import models, portfolio_calc

st.header("Positions")

portfolios = models.get_portfolios()
selected = st.selectbox("Portfolio", [p["id"] for p in portfolios],
                        format_func=lambda x: next(p["name"] for p in portfolios if p["id"] == x))

summary = portfolio_calc.calculate_portfolio_summary(selected)
if not summary:
    st.info("No positions found.")
    st.stop()

total = sum(r["market_value"] for r in summary)
st.metric("Total Portfolio Value", f"{total:,.2f}")

df = pd.DataFrame(summary)

# Colour P&L
def colour_pnl(val):
    if val is None:
        return ""
    return "color: green" if val >= 0 else "color: red"

styled = df[["ticker", "shares", "avg_cost", "current_price", "market_value", "weight", "pnl", "pnl_pct"]].style.map(
    colour_pnl, subset=["pnl", "pnl_pct"]
).format({
    "shares": "{:.2f}",
    "avg_cost": lambda x: f"{x:.2f}" if x else "—",
    "current_price": "{:.2f}",
    "market_value": "{:,.0f}",
    "weight": "{:.1%}",
    "pnl": lambda x: f"{x:,.0f}" if x is not None else "—",
    "pnl_pct": lambda x: f"{x:.1%}" if x is not None else "—",
})

st.dataframe(styled, use_container_width=True, hide_index=True)
