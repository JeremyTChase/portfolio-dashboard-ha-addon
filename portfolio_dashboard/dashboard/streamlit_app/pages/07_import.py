"""Import page — upload Freetrade CSV to update positions."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()
from data_service import models, csv_parser, price_updater, risk_metrics

st.header("Import Portfolio Data")

st.markdown("""
**How to export from Freetrade:**
1. Open the Freetrade app
2. Go to **Activity** tab
3. Tap the calendar icon (top right)
4. Download the CSV export
5. Upload it here
""")

# Account selector
account = st.selectbox("Which account is this export for?", ["sip", "ss_isa"],
                       format_func=lambda x: "SIP (SIPP)" if x == "sip" else "SS ISA")

# File upload
uploaded = st.file_uploader("Upload Freetrade CSV", type=["csv"])

if uploaded:
    # Save to data dir
    data_dir = os.environ.get("PORTFOLIO_DATA_DIR", str(Path(__file__).resolve().parent.parent.parent / "db"))
    save_path = os.path.join(data_dir, f"freetrade_{account}.csv")
    with open(save_path, "wb") as f:
        f.write(uploaded.getvalue())
    st.success(f"File saved: {save_path}")

    # Parse and show preview
    positions = csv_parser.parse_freetrade_csv(save_path)

    if not positions:
        st.error("No positions found in this CSV. Check it's an activity feed export.")
        st.stop()

    st.subheader(f"Parsed {len(positions)} positions:")
    import pandas as pd
    df = pd.DataFrame([
        {"Ticker": t, "Shares": d["shares"], "Avg Cost": d["avg_cost"] or "—"}
        for t, d in sorted(positions.items())
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("Confirm Import", type="primary"):
        with st.spinner("Importing positions and fetching prices..."):
            name = "SIP (SIPP)" if account == "sip" else "SS ISA"
            models.upsert_portfolio(account, name)

            # Capture old positions for transaction log
            old_positions = models.get_positions(account)

            # Clear and re-insert
            for p in old_positions:
                models.delete_position(account, p["ticker"])

            for ticker, data in positions.items():
                models.upsert_position(
                    account, ticker, data["shares"],
                    avg_cost=data["avg_cost"], currency=data["currency"]
                )

            # Log what changed
            new_positions = models.get_positions(account)
            models.log_transactions(account, old_positions, new_positions)

            # Fetch prices and calculate risk
            price_updater.fetch_and_store_prices()
            risk_metrics.calculate_and_store_metrics(account)

            # Take a snapshot
            today = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d")
            total = models.take_position_snapshot(account, today)
            m = models.get_latest_risk_metrics(account)
            if total and m:
                models.insert_risk_metrics_history(account, today, total, m)

        st.success(f"Imported {len(positions)} positions for {name}!")

        # Show what changed
        txns = models.get_transaction_log(account, limit=10)
        if txns:
            st.subheader("Changes detected:")
            for t in txns:
                icon = {"added": "+", "removed": "-", "increased": "^", "decreased": "v"}.get(t["action"], "?")
                st.markdown(f"  {icon} **{t['ticker']}**: {t['action']} ({t['shares_before']:.1f} -> {t['shares_after']:.1f})")

        st.balloons()

st.divider()

# Show current state
st.subheader("Current Portfolios")
for p in models.get_portfolios():
    positions = models.get_positions(p["id"])
    last_import = p["last_import_date"] or "Never"
    st.markdown(f"**{p['name']}**: {len(positions)} positions (last import: {last_import[:10] if last_import != 'Never' else 'Never'})")
