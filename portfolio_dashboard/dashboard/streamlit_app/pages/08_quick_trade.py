"""Quick Trade — log trades directly without CSV upload."""

import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

import os
from data_service import models, price_updater, risk_metrics, csv_parser

st.header("Quick Trade")
st.markdown("Log trades directly — no CSV needed. Just enter what you bought or sold.")

# Account selector
account = st.selectbox("Account", ["sip", "ss_isa"],
                       format_func=lambda x: "SIP (SIPP)" if x == "sip" else "SS ISA")

# Current positions for reference
positions = models.get_positions(account)
current_tickers = {p["ticker"]: p["shares"] for p in positions}

st.divider()

# Trade type
col1, col2 = st.columns(2)
with col1:
    action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
with col2:
    st.markdown("")  # spacer

# Ticker input
if action == "SELL":
    # Show dropdown of current holdings
    ticker = st.selectbox("Ticker", sorted(current_tickers.keys()),
                          format_func=lambda t: f"{t} ({current_tickers[t]:.2f} shares)")
    max_shares = current_tickers.get(ticker, 0)
    st.caption(f"You hold {max_shares:.2f} shares")
else:
    # Free text for buys — could be new ticker
    ticker_input = st.text_input("Ticker (Yahoo Finance format)", placeholder="e.g. MU, AVGO, RR.L")
    ticker = ticker_input.strip().upper()
    if ticker and not ticker.endswith(".L") and "." not in ticker:
        # Might need .L suffix for UK stocks
        st.caption(f"US ticker: **{ticker}** — add **.L** for UK stocks (e.g. RR.L)")

# Shares
shares = st.number_input("Shares", min_value=0.0001, step=1.0, format="%.4f")

# Sell all shortcut
if action == "SELL" and ticker in current_tickers:
    if st.checkbox("Sell entire position"):
        shares = current_tickers[ticker]
        st.info(f"Will sell all {shares:.4f} shares")

# Preview
st.divider()
if ticker and shares > 0:
    if action == "BUY":
        new_shares = current_tickers.get(ticker, 0) + shares
        if ticker in current_tickers:
            st.markdown(f"**{action} {shares:.4f} {ticker}** → position: {current_tickers[ticker]:.4f} + {shares:.4f} = **{new_shares:.4f} shares**")
        else:
            st.markdown(f"**{action} {shares:.4f} {ticker}** → new position: **{new_shares:.4f} shares**")
    else:
        current = current_tickers.get(ticker, 0)
        remaining = current - shares
        if remaining < 0.001:
            st.markdown(f"**{action} {shares:.4f} {ticker}** → **position closed**")
        else:
            st.markdown(f"**{action} {shares:.4f} {ticker}** → remaining: **{remaining:.4f} shares**")

    if st.button("Confirm Trade", type="primary"):
        old_positions = models.get_positions(account)

        if action == "BUY":
            new_total = current_tickers.get(ticker, 0) + shares
            models.upsert_position(account, ticker, new_total)
            st.success(f"Bought {shares:.4f} {ticker} — now hold {new_total:.4f}")
        else:
            remaining = current_tickers.get(ticker, 0) - shares
            if remaining < 0.001:
                models.delete_position(account, ticker)
                st.success(f"Sold all {ticker} — position closed")
            else:
                models.upsert_position(account, ticker, remaining)
                st.success(f"Sold {shares:.4f} {ticker} — now hold {remaining:.4f}")

        # Log the transaction
        new_positions = models.get_positions(account)
        models.log_transactions(account, old_positions, new_positions)

        # Fetch prices for new tickers
        price_updater.fetch_and_store_prices()
        risk_metrics.calculate_and_store_metrics(account)

        # Snapshot
        today = datetime.utcnow().strftime("%Y-%m-%d")
        total = models.take_position_snapshot(account, today)
        m = models.get_latest_risk_metrics(account)
        if total and m:
            models.insert_risk_metrics_history(account, today, total, m)

        st.balloons()
        st.rerun()

st.divider()

# Recent trades log
st.subheader("Recent Activity")
txns = models.get_transaction_log(account, limit=15)
if txns:
    for t in txns:
        icon = {"added": "🟢", "removed": "🔴", "increased": "⬆️", "decreased": "⬇️"}.get(t["action"], "❓")
        date = t["logged_at"][:16]
        st.markdown(f"{icon} **{t['ticker']}** {t['action']} ({t['shares_before']:.1f} → {t['shares_after']:.1f}) — {date}")
else:
    st.caption("No recent trades logged")
