"""Market page — macro indicators + RSS news feed."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

from components.agent_chat import render_chat_sidebar
render_chat_sidebar(page_name="market")
import yaml

from data_service import models

st.header("Market & Macro")

# Macro indicators
st.subheader("Macro Indicators")
macro = models.get_latest_macro()

INDICATOR_LABELS = {
    "^VIX": ("VIX (Fear Index)", "Higher = more volatility/fear"),
    "GC=F": ("Gold (USD/oz)", "Safe haven — rises in uncertainty"),
    "CL=F": ("WTI Crude Oil (USD)", "Key for energy, inflation"),
    "^TNX": ("US 10Y Yield (%)", "Higher = tighter financial conditions"),
    "GBPUSD=X": ("GBP/USD", "Sterling strength vs Dollar"),
}

if macro:
    cols = st.columns(len(macro))
    for i, (indicator, data) in enumerate(macro.items()):
        label, tooltip = INDICATOR_LABELS.get(indicator, (indicator, ""))
        with cols[i]:
            st.metric(label, f"{data['value']:.2f}", help=tooltip)
            st.caption(f"As of: {data['date']}")
else:
    st.info("No macro data loaded. Run price updater to fetch.")

st.divider()

# News feed
st.subheader("Market News")

try:
    import feedparser
except ImportError:
    st.warning("Install feedparser: `pip install feedparser`")
    st.stop()

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
with open(_BASE_DIR / "app_config.yaml") as f:
    cfg = yaml.safe_load(f)

feeds = cfg.get("news_feeds", [])

for feed_url in feeds:
    try:
        feed = feedparser.parse(feed_url)
        st.markdown(f"**{feed.feed.get('title', feed_url)}**")
        for entry in feed.entries[:5]:
            published = entry.get("published", "")
            st.markdown(f"- [{entry.title}]({entry.link}) — {published[:16]}")
    except Exception as e:
        st.error(f"Error loading feed: {e}")

st.divider()

# Portfolio-specific macro context
st.subheader("Macro Risk Exposure")
st.markdown("""
**Your holdings and macro risks:**

| Risk Factor | Exposed Holdings | Impact |
|---|---|---|
| Middle East / Oil | RR.L, AAL.L, ISF.L, IUSA.L | Oil prices affect energy costs, defence spending benefits RR/BAB |
| Trade Wars / Tariffs | NVDA, TSLA, DELL, INTC, ASML | US-China tension, semiconductor export controls |
| UK Interest Rates | BARC.L, HSBA.L, PSN.L, DGE.L | Rate cuts help property/consumer; banks prefer higher rates |
| Defence Spending | BAB.L, RR.L | NATO/UK budget increases are tailwind |
| GBP/USD | ~30% US-listed in SIP | Weaker GBP boosts US holdings in GBP terms |
""")
