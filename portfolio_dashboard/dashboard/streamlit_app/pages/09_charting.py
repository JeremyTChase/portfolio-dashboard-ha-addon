"""Technical Analysis — interactive charting with indicators."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

from components.agent_chat import render_chat_sidebar

from data_service import ohlcv_fetcher, technical_analysis, chart_builder, ticker_lookup, models
from data_service.ibkr_client import IBKRClient, IB_AVAILABLE

st.header("Technical Analysis")
st.caption("Interactive charting with technical indicators. Hover over any **?** icon for a quick explanation.")

# -----------------------------------------------------------------------
# IBKR connection (sidebar, top)
# -----------------------------------------------------------------------
ibkr_client = None
use_ibkr_data = False

with st.sidebar:
    st.subheader("Data Source")
    if IB_AVAILABLE:
        if "ibkr_client" not in st.session_state:
            st.session_state["ibkr_client"] = IBKRClient()

        ibkr_client = st.session_state["ibkr_client"]

        if ibkr_client.is_connected():
            st.success("IBKR: Connected")
            if st.button("Disconnect", key="ibkr_disconnect"):
                ibkr_client.disconnect()
                st.rerun()
            use_ibkr_data = st.checkbox("Use IBKR data (real-time)", value=False, key="use_ibkr")
        else:
            st.info("IBKR: Not connected")
            if st.button("Connect to IBKR", key="ibkr_connect"):
                with st.spinner("Connecting..."):
                    if ibkr_client.connect():
                        st.rerun()
                    else:
                        st.error("Connection failed — is TWS/Gateway running?")
    else:
        st.caption("IBKR not available (install ib_async)")

    st.caption("Using: **IBKR**" if use_ibkr_data else "Using: **yfinance**")
    st.divider()

# -----------------------------------------------------------------------
# Top controls
# -----------------------------------------------------------------------
col_search, col_period, col_info = st.columns([3, 1, 1])

with col_search:
    search_query = st.text_input(
        "Search ticker or company",
        placeholder="e.g. AAPL, Rolls Royce, Bitcoin, BARC.L...",
        key="chart_search",
        help="Enter a stock ticker (e.g. AAPL, RR.L) or company name. UK stocks use the .L suffix for London Stock Exchange.",
    )

with col_period:
    period = st.selectbox(
        "Timeframe", ["1M", "3M", "6M", "1Y", "2Y", "5Y"], index=3,
        help="How far back to look. Shorter timeframes (1M, 3M) are better for trading signals. Longer (1Y, 2Y, 5Y) show the bigger trend.",
    )

# Ticker resolution
ticker = None

# Quick-access: show portfolio tickers as buttons
all_tickers = models.get_all_tickers()
if all_tickers and not search_query:
    st.caption("Your holdings:")
    cols = st.columns(min(len(all_tickers), 8))
    for i, t in enumerate(sorted(all_tickers)):
        with cols[i % min(len(all_tickers), 8)]:
            if st.button(t, key=f"quick_{t}", use_container_width=True):
                ticker = t

# Search results
if search_query and len(search_query) >= 2:
    if search_query.upper() in [t.upper() for t in all_tickers]:
        ticker = search_query.upper()
    else:
        results = ticker_lookup.search_tickers(search_query)
        if results:
            options = {f"{r['name']} ({r['symbol']}) — {r['exchange']}": r["symbol"] for r in results}
            selected = st.radio("Select:", list(options.keys()), key="chart_results")
            ticker = options[selected]
        else:
            ticker = search_query.strip().upper()
            st.info(f"No search results — trying **{ticker}** directly.")

if not ticker:
    st.info("Enter a ticker symbol or company name above to view the chart.")
    st.stop()

with col_info:
    st.metric("Ticker", ticker)

# -----------------------------------------------------------------------
# Sidebar: indicator controls with tooltips
# -----------------------------------------------------------------------
with st.sidebar:
    st.subheader("Indicators")
    st.caption("Toggle indicators on/off. Hover **?** for explanations.")

    show_sma = st.checkbox(
        "SMA (Simple Moving Average)", value=True,
        help="A smoothed line showing the average closing price over N days. "
             "When price is ABOVE the SMA, the trend is generally bullish. "
             "When BELOW, bearish. The 200-day SMA is widely watched — "
             "a 'golden cross' (50 crosses above 200) is a strong buy signal.",
    )
    sma_periods = []
    if show_sma:
        sma_periods = st.multiselect(
            "SMA Periods", [10, 20, 50, 100, 200], default=[20, 50, 200], key="sma_p",
            help="20 = short-term trend, 50 = medium-term, 200 = long-term. "
                 "Most traders watch the 50 and 200 together.",
        )

    show_ema = st.checkbox(
        "EMA (Exponential Moving Average)", value=True,
        help="Like SMA but gives MORE weight to recent prices, so it reacts "
             "faster to price changes. The 9 and 21 EMAs are popular for "
             "spotting short-term momentum shifts. When the 9 EMA crosses "
             "above the 21 EMA, it suggests upward momentum.",
    )
    ema_periods = []
    if show_ema:
        ema_periods = st.multiselect(
            "EMA Periods", [9, 12, 21, 50], default=[9, 21], key="ema_p",
            help="9 = very responsive (day trading), 21 = swing trading, "
                 "50 = medium-term trend following.",
        )

    show_rsi = st.checkbox(
        "RSI (Relative Strength Index)", value=True,
        help="Measures how fast price is rising or falling on a scale of 0-100. "
             "Above 70 = OVERBOUGHT (price may drop soon). "
             "Below 30 = OVERSOLD (price may bounce soon). "
             "Between 30-70 = neutral. The default length of 14 days works for most situations.",
    )
    rsi_length = 14
    if show_rsi:
        rsi_length = st.number_input(
            "RSI Length", min_value=2, max_value=50, value=14, key="rsi_l",
            help="Number of periods to calculate RSI. 14 is the standard. "
                 "Lower = more sensitive (more signals, more false alarms). "
                 "Higher = smoother (fewer signals, more reliable).",
        )

    show_macd = st.checkbox(
        "MACD (Moving Average Convergence Divergence)", value=True,
        help="Shows the relationship between two EMAs. The MACD has three parts: "
             "1) MACD line (blue) = fast EMA minus slow EMA. "
             "2) Signal line (orange) = smoothed MACD. "
             "3) Histogram (bars) = difference between MACD and signal. "
             "BUY signal: MACD crosses ABOVE signal line. "
             "SELL signal: MACD crosses BELOW signal line. "
             "Green histogram bars = bullish momentum increasing.",
    )
    macd_fast, macd_slow, macd_signal = 12, 26, 9
    if show_macd:
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            macd_fast = st.number_input("Fast", min_value=2, max_value=50, value=12, key="macd_f",
                                        help="Fast EMA period (default 12)")
        with mc2:
            macd_slow = st.number_input("Slow", min_value=5, max_value=100, value=26, key="macd_s",
                                        help="Slow EMA period (default 26)")
        with mc3:
            macd_signal = st.number_input("Signal", min_value=2, max_value=50, value=9, key="macd_sig",
                                          help="Signal smoothing (default 9)")

    show_bbands = st.checkbox(
        "Bollinger Bands", value=False,
        help="A volatility band around the price. The upper and lower bands are "
             "2 standard deviations from the middle (20-day SMA). "
             "When price touches the UPPER band = potentially overbought. "
             "When price touches the LOWER band = potentially oversold. "
             "When bands SQUEEZE (narrow), a big move is coming. "
             "When bands EXPAND, volatility is high.",
    )
    bb_length, bb_std = 20, 2.0
    if show_bbands:
        bb_length = st.number_input("BB Length", min_value=5, max_value=100, value=20, key="bb_l",
                                    help="Number of periods for the middle band (SMA)")
        bb_std = st.number_input("BB Std Dev", min_value=0.5, max_value=5.0, value=2.0, step=0.5, key="bb_s",
                                 help="Width of the bands. 2.0 is standard. Higher = wider bands, fewer touches.")

    st.divider()
    st.page_link("pages/10_learning.py", label="Learn more about indicators", icon="📚")

# -----------------------------------------------------------------------
# Fetch data and compute indicators
# -----------------------------------------------------------------------
with st.spinner(f"Loading {ticker} data..."):
    _ibkr = ibkr_client if use_ibkr_data else None
    df = ohlcv_fetcher.get_ohlcv_df(ticker, period=period, ibkr_client=_ibkr)

if df.empty:
    st.error(f"No data available for **{ticker}**. Check the ticker symbol and try again.")
    st.stop()

# Build indicator config from sidebar selections
indicators = {}
if sma_periods:
    indicators["sma"] = sma_periods
if ema_periods:
    indicators["ema"] = ema_periods
if show_rsi:
    indicators["rsi"] = {"length": rsi_length}
if show_macd:
    indicators["macd"] = {"fast": macd_fast, "slow": macd_slow, "signal": macd_signal}
if show_bbands:
    indicators["bbands"] = {"length": bb_length, "std": bb_std}

# Compute indicators
if indicators:
    df = technical_analysis.compute_indicators(df, indicators)

# Build overlays list — all indicator columns
base_cols = {"date", "open", "high", "low", "close", "volume", "ticker", "currency", "source"}
overlays = [c for c in df.columns if c not in base_cols]

# -----------------------------------------------------------------------
# Chart
# -----------------------------------------------------------------------
fig = chart_builder.build_candlestick_chart(
    df, ticker, show_volume=True, overlays=overlays, height=700
)

# -----------------------------------------------------------------------
# Apply agent-queued hypothesis overlays from st.session_state
# (populated by components.agent_chat when the LLM calls chart_* tools)
# -----------------------------------------------------------------------
_hyp = st.session_state.get("chart_hypotheses") or {}
_hlines = _hyp.get("hlines") or []
_annotations = _hyp.get("annotations") or []
_positions = _hyp.get("positions") or []

for _h in _hlines:
    try:
        fig.add_hline(
            y=float(_h["price"]),
            line_dash="dash",
            line_color=_h.get("color", "orange"),
            annotation_text=_h.get("label", ""),
            annotation_position="top right",
        )
    except Exception:
        pass

for _a in _annotations:
    try:
        fig.add_annotation(
            x=_a["date"], y=float(df["close"].iloc[-1]),
            text=_a.get("text", ""),
            showarrow=True, arrowhead=2, arrowcolor="purple",
            bgcolor="rgba(128, 0, 128, 0.15)", bordercolor="purple",
        )
    except Exception:
        pass

for _p in _positions:
    try:
        fig.add_hline(
            y=float(_p["price"]),
            line_dash="dot",
            line_color="green" if _p.get("action") == "buy" else "red",
            annotation_text=f"{_p['action'].upper()} {_p.get('shares','?')}@{_p.get('price')}"
                            + (f" — {_p['note']}" if _p.get("note") else ""),
            annotation_position="bottom right",
        )
    except Exception:
        pass

# Show a "clear hypotheses" button if there are any overlays
if _hlines or _annotations or _positions:
    cl_cols = st.columns([4, 1])
    with cl_cols[1]:
        if st.button("🗑 Clear hypotheses", key="clear_chart_hypotheses",
                     use_container_width=True):
            st.session_state["chart_hypotheses"] = {
                "hlines": [], "annotations": [], "positions": [],
            }
            st.rerun()
    with cl_cols[0]:
        st.caption(
            f"💭 Showing {len(_hlines)} hypothesis line(s), "
            f"{len(_annotations)} annotation(s), {len(_positions)} position(s) "
            "from JezFinanceClaw"
        )

st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------
# Reading the chart — inline guide
# -----------------------------------------------------------------------
with st.expander("How to read this chart", icon="💡"):
    st.markdown("""
**Candlesticks** — Each candle represents one day of trading:
- **Green candle** = price went UP (closed higher than it opened)
- **Red candle** = price went DOWN (closed lower than it opened)
- **Body** (thick part) = range between open and close
- **Wicks** (thin lines) = the high and low for the day

**Volume bars** (below price) — How many shares were traded. High volume on a price move = strong conviction. Low volume = weak move, could reverse.

**What to look for:**
- Price bouncing off an SMA line = that line is acting as **support** (below) or **resistance** (above)
- RSI above 70 while price is at a peak = **potential reversal down**
- MACD histogram flipping from red to green = **momentum shifting bullish**
- Price touching the lower Bollinger Band with RSI below 30 = **potential buying opportunity**

*These are guidelines, not guarantees. Always consider the bigger picture.*
    """)

# -----------------------------------------------------------------------
# Key stats with tooltips
# -----------------------------------------------------------------------
st.subheader("Key Stats")
last_row = df.iloc[-1]
prev_row = df.iloc[-2] if len(df) > 1 else last_row

current_price = last_row["close"]
prev_close = prev_row["close"]
day_change = current_price - prev_close
day_change_pct = (day_change / prev_close) * 100 if prev_close else 0

currency = "GBX" if ticker.endswith(".L") else "USD"
currency_sym = "p" if currency == "GBX" else "$"

stat_cols = st.columns(5)

with stat_cols[0]:
    st.metric(
        "Current Price", f"{currency_sym}{current_price:,.2f}", f"{day_change_pct:+.2f}%",
        help="The most recent closing price and the change from the previous day. "
             "Green = price went up, Red = price went down.",
    )

with stat_cols[1]:
    vol = last_row.get("volume", 0)
    vol_str = f"{vol:,.0f}" if vol else "N/A"
    st.metric(
        "Volume", vol_str,
        help="Number of shares traded in the last session. High volume on a price move "
             "means strong conviction behind the move. Low volume moves are less reliable.",
    )

with stat_cols[2]:
    rsi_col = f"RSI_{rsi_length}" if show_rsi else None
    if rsi_col and rsi_col in df.columns:
        rsi_val = last_row[rsi_col]
        signal = technical_analysis.rsi_signal(rsi_val)
        st.metric(
            "RSI", f"{rsi_val:.1f}", signal,
            help="Relative Strength Index (0-100). "
                 "Above 70 = Overbought (price may be due for a pullback). "
                 "Below 30 = Oversold (price may be due for a bounce). "
                 "30-70 = Neutral territory.",
        )
    else:
        st.metric("RSI", "—", help="Enable RSI in the sidebar to see this value.")

with stat_cols[3]:
    sma_200_col = "SMA_200" if "SMA_200" in df.columns else None
    if sma_200_col:
        sma_val = last_row[sma_200_col]
        signal = technical_analysis.price_vs_sma(current_price, sma_val)
        st.metric(
            "vs SMA 200", signal,
            f"{currency_sym}{sma_val:,.2f}" if pd.notna(sma_val) else "N/A",
            help="Whether the current price is above or below the 200-day Simple Moving Average. "
                 "ABOVE = generally in an uptrend (bullish). "
                 "BELOW = generally in a downtrend (bearish). "
                 "The 200 SMA is one of the most widely followed indicators by institutional investors.",
        )
    else:
        st.metric("vs SMA 200", "—", help="Add 200 to SMA periods in the sidebar to see this.")

with stat_cols[4]:
    high_52 = df["high"].max()
    low_52 = df["low"].min()
    pct_from_high = ((current_price - high_52) / high_52) * 100 if high_52 else 0
    st.metric(
        "From Period High", f"{pct_from_high:+.1f}%",
        f"H: {currency_sym}{high_52:,.2f} / L: {currency_sym}{low_52:,.2f}",
        help="How far the current price is from the highest point in the selected timeframe. "
             "A stock near its high (0% to -5%) may have strong momentum. "
             "A stock far from its high (-20%+) could be a value opportunity — or in trouble.",
    )

# -----------------------------------------------------------------------
# Data table (expandable)
# -----------------------------------------------------------------------
with st.expander("Raw OHLCV Data"):
    st.caption("**O**pen, **H**igh, **L**ow, **C**lose, **V**olume — the five key data points for each trading day.")
    display_df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    display_df = display_df.sort_values("date", ascending=False)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

# ── Agent chat sidebar ─────────────────────────────────────────────────
render_chat_sidebar(
    page_name="charting",
    page_context={
        "ticker": ticker,
        "timeframe": period,
        "current_price": float(current_price) if current_price else None,
        "indicators_enabled": list(indicators.keys()) if indicators else [],
        "active_hypotheses": st.session_state.get("chart_hypotheses"),
    },
)
