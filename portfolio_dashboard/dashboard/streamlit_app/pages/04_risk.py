"""Risk page — metrics, correlation heatmap, drawdown chart."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

from components.agent_chat import render_chat_sidebar
render_chat_sidebar(page_name="risk")
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from data_service import models, risk_metrics as rm_module

st.header("Risk Metrics")

portfolios = models.get_portfolios()
selected = st.selectbox("Portfolio", [p["id"] for p in portfolios],
                        format_func=lambda x: next(p["name"] for p in portfolios if p["id"] == x))

# Show stored metrics
metrics = models.get_latest_risk_metrics(selected)

if metrics:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Volatility (ann.)", f"{metrics['volatility_annual']:.1%}" if metrics['volatility_annual'] else "N/A")
    c2.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}" if metrics['sharpe_ratio'] else "N/A")
    c3.metric("Sortino Ratio", f"{metrics['sortino_ratio']:.2f}" if metrics['sortino_ratio'] else "N/A")
    c4.metric("Max Drawdown", f"{metrics['max_drawdown']:.1%}" if metrics['max_drawdown'] else "N/A")
    c5.metric("CVaR (95%)", f"{metrics['cvar_95']:.2%}" if metrics['cvar_95'] else "N/A")
    st.caption(f"Calculated: {metrics['calculated_at'][:19]}")
else:
    st.info("No risk metrics calculated yet. Run the price updater first.")

# Recalculate button
if st.button("Recalculate Risk Metrics"):
    with st.spinner("Calculating..."):
        new_metrics = rm_module.calculate_and_store_metrics(selected)
        if new_metrics:
            st.success("Metrics updated!")
            st.rerun()
        else:
            st.error("Could not calculate — check that prices are loaded.")

# Correlation heatmap
st.subheader("Return Correlations")
positions = models.get_positions(selected)
if positions:
    tickers = [p["ticker"] for p in positions]
    returns_df = rm_module._get_returns_df(tickers, lookback_days=252)

    if not returns_df.empty:
        corr = returns_df.corr()
        fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r",
                        zmin=-1, zmax=1, aspect="auto")
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

        # Drawdown chart
        st.subheader("Portfolio Drawdown (1 Year)")
        from data_service import portfolio_calc
        summary = portfolio_calc.calculate_portfolio_summary(selected)
        weights = {r["ticker"]: r["weight"] for r in summary if r["ticker"] in returns_df.columns}
        available = [t for t in returns_df.columns if t in weights]

        if available:
            w = np.array([weights[t] for t in available])
            w = w / w.sum()
            port_returns = returns_df[available].values @ w
            cumulative = np.cumprod(1 + port_returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (running_max - cumulative) / running_max

            dd_df = pd.DataFrame({
                "Date": returns_df.index[-len(drawdown):],
                "Drawdown": -drawdown
            })
            fig = px.area(dd_df, x="Date", y="Drawdown", color_discrete_sequence=["#ff6b6b"])
            fig.update_layout(yaxis_tickformat=".0%", height=300)
            st.plotly_chart(fig, use_container_width=True)
