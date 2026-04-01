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

from data_service import models, price_updater, risk_metrics, ticker_lookup

st.header("Quick Trade")
st.markdown("Log trades directly — no CSV needed.")

# Account selector
account = st.selectbox("Account", ["sip", "ss_isa"],
                       format_func=lambda x: "SIP (SIPP)" if x == "sip" else "SS ISA")

# Current positions with names
positions = models.get_positions(account)
current_tickers = {p["ticker"]: p["shares"] for p in positions}
names = ticker_lookup.get_company_names(list(current_tickers.keys())) if current_tickers else {}

st.divider()

# Trade type
action = st.radio("Action", ["BUY", "SELL"], horizontal=True)

# Ticker input
ticker = None
if action == "SELL":
    ticker = st.selectbox("Sell from", sorted(current_tickers.keys()),
                          format_func=lambda t: f"{names.get(t, t)} ({t}) — {current_tickers[t]:.2f} shares")
    max_shares = current_tickers.get(ticker, 0)
else:
    # Search-as-you-type for buys
    search_query = st.text_input("Search company or ticker", placeholder="e.g. Micron, Rolls Royce, AVGO...")

    if search_query and len(search_query) >= 2:
        results = ticker_lookup.search_tickers(search_query)
        if results:
            options = {f"{r['name']} ({r['symbol']}) — {r['exchange']}": r['symbol'] for r in results}
            selected = st.radio("Select:", list(options.keys()))
            ticker = options[selected]
            st.success(f"Selected: **{ticker}**")
        else:
            st.warning("No results found. You can enter a ticker directly below.")
            manual = st.text_input("Or enter ticker manually", placeholder="e.g. MU")
            ticker = manual.strip().upper() if manual else None

# Shares
shares = 0.0
if ticker:
    shares = st.number_input("Shares", min_value=0.0001, step=1.0, format="%.4f")

    if action == "SELL" and ticker in current_tickers:
        if st.checkbox("Sell entire position"):
            shares = current_tickers[ticker]
            st.info(f"Will sell all {shares:.4f} shares")

# Preview and confirm
st.divider()
if ticker and shares > 0:
    name = names.get(ticker) or ticker_lookup.get_company_name(ticker)

    if action == "BUY":
        new_shares = current_tickers.get(ticker, 0) + shares
        if ticker in current_tickers:
            st.markdown(f"**BUY {shares:.4f} {name} ({ticker})** → {current_tickers[ticker]:.4f} + {shares:.4f} = **{new_shares:.4f} shares**")
        else:
            st.markdown(f"**BUY {shares:.4f} {name} ({ticker})** → new position: **{new_shares:.4f} shares**")
    else:
        current = current_tickers.get(ticker, 0)
        remaining = current - shares
        if remaining < 0.001:
            st.markdown(f"**SELL {shares:.4f} {name} ({ticker})** → **position closed**")
        else:
            st.markdown(f"**SELL {shares:.4f} {name} ({ticker})** → remaining: **{remaining:.4f} shares**")

    if st.button("Confirm Trade", type="primary"):
        old_positions = models.get_positions(account)

        if action == "BUY":
            new_total = current_tickers.get(ticker, 0) + shares
            models.upsert_position(account, ticker, new_total)
            st.success(f"Bought {shares:.4f} {name} ({ticker}) — now hold {new_total:.4f}")
        else:
            remaining = current_tickers.get(ticker, 0) - shares
            if remaining < 0.001:
                models.delete_position(account, ticker)
                st.success(f"Sold all {name} ({ticker}) — position closed")
            else:
                models.upsert_position(account, ticker, remaining)
                st.success(f"Sold {shares:.4f} {name} ({ticker}) — now hold {remaining:.4f}")

        new_positions = models.get_positions(account)
        models.log_transactions(account, old_positions, new_positions)

        price_updater.fetch_and_store_prices()
        risk_metrics.calculate_and_store_metrics(account)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        total = models.take_position_snapshot(account, today)
        m = models.get_latest_risk_metrics(account)
        if total and m:
            models.insert_risk_metrics_history(account, today, total, m)

        st.balloons()
        st.rerun()

st.divider()

# Recent activity
st.subheader("Recent Activity")
txns = models.get_transaction_log(account, limit=15)
if txns:
    for t in txns:
        icon = {"added": "🟢", "removed": "🔴", "increased": "⬆️", "decreased": "⬇️"}.get(t["action"], "❓")
        date = t["logged_at"][:16]
        tname = names.get(t["ticker"]) or t["ticker"]
        st.markdown(f"{icon} **{tname}** ({t['ticker']}) {t['action']} ({t['shares_before']:.1f} → {t['shares_after']:.1f}) — {date}")
else:
    st.caption("No recent trades logged")
