"""Agent page — AI analysis log and alerts."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

from components.agent_chat import render_chat_sidebar
render_chat_sidebar(page_name="agent_logs")
from data_service import models

st.header("AI Agent")

SEVERITY_ICONS = {"info": "ℹ️", "warning": "⚠️", "alert": "🚨"}

# Tabs for different log types
tab_all, tab_daily, tab_alerts, tab_weekly = st.tabs(
    ["All", "Daily Analysis", "Price Alerts", "Weekly Review"]
)

task_filter = {
    "All": None,
    "Daily Analysis": "daily_analysis",
    "Price Alerts": "price_alert",
    "Weekly Review": "weekly_review",
}

for tab, (label, task_type) in zip(
    [tab_all, tab_daily, tab_alerts, tab_weekly], task_filter.items()
):
    with tab:
        logs = models.get_agent_logs(task_type=task_type, limit=20)

        if not logs:
            st.info(f"No {label.lower()} entries yet. The agent service will populate this.")
            continue

        for log in logs:
            icon = SEVERITY_ICONS.get(log["severity"], "")
            with st.expander(
                f"{icon} {log['created_at'][:16]} — {log['summary'][:80]}",
                expanded=(log == logs[0]),
            ):
                st.markdown(log["full_analysis"] or log["summary"])
                st.caption(f"Type: {log['task_type']} | Severity: {log['severity']}")
