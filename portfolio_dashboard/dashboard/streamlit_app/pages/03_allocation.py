"""Allocation page — pie and bar charts, geographic split."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

from components.agent_chat import render_chat_sidebar
render_chat_sidebar(page_name="allocation")
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from data_service import models, portfolio_calc

st.header("Allocation")

portfolios = models.get_portfolios()
selected = st.selectbox("Portfolio", [p["id"] for p in portfolios],
                        format_func=lambda x: next(p["name"] for p in portfolios if p["id"] == x))

summary = portfolio_calc.calculate_portfolio_summary(selected)
if not summary:
    st.info("No positions found.")
    st.stop()

df = pd.DataFrame(summary)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Allocation by Holding")
    fig = px.pie(df, values="market_value", names="ticker",
                 hole=0.4, color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_traces(textposition="inside", textinfo="label+percent")
    fig.update_layout(showlegend=False, height=450)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Weight Bar Chart")
    fig = px.bar(df, x="weight", y="ticker", orientation="h",
                 color="weight", color_continuous_scale="Blues")
    fig.update_layout(yaxis=dict(autorange="reversed"), height=450,
                      xaxis_title="Weight", yaxis_title="", coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

# Geographic split
st.subheader("Geographic Exposure")
df["region"] = df["ticker"].apply(lambda t: "UK" if t.endswith(".L") else "US/Intl")
geo_df = df.groupby("region")["market_value"].sum().reset_index()
fig = px.pie(geo_df, values="market_value", names="region",
             color_discrete_map={"UK": "#1f77b4", "US/Intl": "#ff7f0e"})
fig.update_layout(height=300)
st.plotly_chart(fig, use_container_width=True)
