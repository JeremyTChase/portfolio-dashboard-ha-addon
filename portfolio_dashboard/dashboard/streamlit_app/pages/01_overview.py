"""Overview page — combined SIP + ISA summary."""

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

st.header("Portfolio Overview")

portfolios = models.get_portfolios()
if not portfolios:
    st.info("No portfolios loaded.")
    st.stop()

for p in portfolios:
    pid = p["id"]
    summary = portfolio_calc.calculate_portfolio_summary(pid)
    if not summary:
        continue

    total = sum(r["market_value"] for r in summary)
    top = summary[0]  # already sorted by weight desc

    with st.expander(f"{p['name']} — {total:,.0f}", expanded=True):
        # Top-level metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Value", f"{total:,.0f}")
        c2.metric("Holdings", len(summary))
        c3.metric("Top Holding", f"{top['ticker']} ({top['weight']:.1%})")

        rm = models.get_latest_risk_metrics(pid)
        if rm and rm["sharpe_ratio"]:
            c4.metric("Sharpe Ratio", f"{rm['sharpe_ratio']:.2f}")

        # Quick positions table
        df = pd.DataFrame(summary)
        df["weight"] = df["weight"].map("{:.1%}".format)
        df["market_value"] = df["market_value"].map("{:,.0f}".format)
        if "pnl_pct" in df.columns:
            df["pnl_pct"] = df["pnl_pct"].apply(lambda x: f"{x:.1%}" if x is not None else "—")
        st.dataframe(
            df[["ticker", "shares", "current_price", "market_value", "weight", "pnl_pct"]],
            use_container_width=True, hide_index=True,
        )
