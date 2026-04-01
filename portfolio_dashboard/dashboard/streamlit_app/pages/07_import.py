"""Import page — upload Freetrade CSV to update positions."""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

import pandas as pd
from data_service import models, csv_parser, price_updater, risk_metrics

st.header("Import Portfolio Data")

st.markdown("""
**How to export from Freetrade:**
1. Open Freetrade web or app
2. Go to **Activity** tab
3. Download CSV export (3, 6, or 12 months)
4. Upload it here — the system will detect new trades only
""")

# Account selector
account = st.selectbox("Which account is this export for?", ["sip", "ss_isa"],
                       format_func=lambda x: "SIP (SIPP)" if x == "sip" else "SS ISA")

# Import mode
existing = models.get_positions(account)
if existing:
    st.info(f"**{len(existing)} positions already loaded.** New CSV will be merged — only trades after your last import will be applied.")
    import_mode = "delta"
else:
    st.warning("No existing positions. The full CSV will be used to calculate positions from scratch.")
    import_mode = "full"

# File upload
uploaded = st.file_uploader("Upload Freetrade CSV", type=["csv"])

if uploaded:
    data_dir = os.environ.get("PORTFOLIO_DATA_DIR", str(Path(__file__).resolve().parent.parent.parent / "db"))
    save_path = os.path.join(data_dir, f"freetrade_{account}.csv")
    with open(save_path, "wb") as f:
        f.write(uploaded.getvalue())

    if import_mode == "delta" and existing:
        # Delta mode: find last import date, extract only new trades
        last_dates = [p["last_updated"] for p in existing if p["last_updated"]]
        if last_dates:
            since = max(last_dates)[:10]  # YYYY-MM-DD
        else:
            since = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

        st.markdown(f"Looking for trades **after {since}**...")
        trades = csv_parser.parse_freetrade_csv_delta(save_path, since)

        if not trades:
            st.success("No new trades found — your positions are up to date!")
            st.stop()

        st.subheader(f"Found {len(trades)} new trades:")
        trade_df = pd.DataFrame(trades)
        st.dataframe(trade_df[["date", "action", "ticker", "shares", "price"]],
                     use_container_width=True, hide_index=True)

        # Preview what positions will look like
        new_positions = csv_parser.apply_trades_to_positions(existing, trades)
        st.subheader("Positions after applying trades:")
        preview = pd.DataFrame([
            {"Ticker": t, "Shares": d["shares"]}
            for t, d in sorted(new_positions.items())
        ])
        st.dataframe(preview, use_container_width=True, hide_index=True)

        if st.button("Apply Trades", type="primary"):
            with st.spinner("Applying trades and updating prices..."):
                name = "SIP (SIPP)" if account == "sip" else "SS ISA"
                models.upsert_portfolio(account, name)

                # Capture old for transaction log
                old_positions = models.get_positions(account)

                # Clear and re-insert updated positions
                for p in old_positions:
                    models.delete_position(account, p["ticker"])
                for ticker, data in new_positions.items():
                    models.upsert_position(
                        account, ticker, data["shares"],
                        avg_cost=data.get("avg_cost"), currency=data.get("currency", "GBP")
                    )

                # Log changes
                new_pos_rows = models.get_positions(account)
                models.log_transactions(account, old_positions, new_pos_rows)

                # Update prices and risk
                price_updater.fetch_and_store_prices()
                risk_metrics.calculate_and_store_metrics(account)

                # Snapshot
                today = datetime.utcnow().strftime("%Y-%m-%d")
                total = models.take_position_snapshot(account, today)
                m = models.get_latest_risk_metrics(account)
                if total and m:
                    models.insert_risk_metrics_history(account, today, total, m)

            st.success(f"Applied {len(trades)} trades to {name}!")

            txns = models.get_transaction_log(account, limit=10)
            if txns:
                st.subheader("Changes:")
                for t in txns:
                    icon = {"added": "+", "removed": "-", "increased": "^", "decreased": "v"}.get(t["action"], "?")
                    st.markdown(f"  {icon} **{t['ticker']}**: {t['action']} ({t['shares_before']:.1f} -> {t['shares_after']:.1f})")
            st.balloons()

    else:
        # Full mode: calculate from scratch (first import or explicit)
        positions = csv_parser.parse_freetrade_csv(save_path)

        if not positions:
            st.error("No positions found in this CSV.")
            st.stop()

        st.subheader(f"Parsed {len(positions)} positions:")
        df = pd.DataFrame([
            {"Ticker": t, "Shares": d["shares"], "Avg Cost": d["avg_cost"] or "—"}
            for t, d in sorted(positions.items())
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("Confirm Import", type="primary"):
            with st.spinner("Importing positions and fetching prices..."):
                name = "SIP (SIPP)" if account == "sip" else "SS ISA"
                models.upsert_portfolio(account, name)

                for ticker, data in positions.items():
                    models.upsert_position(
                        account, ticker, data["shares"],
                        avg_cost=data["avg_cost"], currency=data["currency"]
                    )

                price_updater.fetch_and_store_prices()
                risk_metrics.calculate_and_store_metrics(account)

                today = datetime.utcnow().strftime("%Y-%m-%d")
                total = models.take_position_snapshot(account, today)
                m = models.get_latest_risk_metrics(account)
                if total and m:
                    models.insert_risk_metrics_history(account, today, total, m)

            st.success(f"Imported {len(positions)} positions for {name}!")
            st.balloons()

st.divider()

# Show current state
st.subheader("Current Portfolios")
for p in models.get_portfolios():
    pos = models.get_positions(p["id"])
    last_dates = [pp["last_updated"] for pp in pos if pp["last_updated"]]
    last = max(last_dates)[:10] if last_dates else "Never"
    st.markdown(f"**{p['name']}**: {len(pos)} positions (last updated: {last})")
