"""Learning Guide — understand technical analysis indicators."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

# Auth check
if not st.session_state.get("authenticated"):
    st.warning("Please log in from the main page.")
    st.stop()

st.header("📚 Technical Analysis Guide")
st.markdown("A practical guide to reading charts and understanding the indicators on the **Technical Analysis** page.")

# -----------------------------------------------------------------------
# Candlesticks
# -----------------------------------------------------------------------
st.subheader("🕯️ Candlestick Charts")
st.markdown("""
Candlestick charts are the standard way to view price action. Each candle shows four pieces of information for a single time period (usually one day):

| Part | What it means |
|------|---------------|
| **Open** | The price at the start of the day |
| **Close** | The price at the end of the day |
| **High** | The highest price reached during the day |
| **Low** | The lowest price reached during the day |

**Green candle** = the price closed HIGHER than it opened (bullish day)
**Red candle** = the price closed LOWER than it opened (bearish day)

The **body** (thick part) shows the range between open and close. The **wicks** (thin lines above/below) show the high and low.

**Key patterns to recognise:**
- **Long green candle** = strong buying pressure
- **Long red candle** = strong selling pressure
- **Small body with long wicks** (called a "doji") = indecision, potential reversal
- **Several green candles in a row** = uptrend
- **Several red candles in a row** = downtrend
""")

# -----------------------------------------------------------------------
# Volume
# -----------------------------------------------------------------------
st.subheader("📊 Volume")
st.markdown("""
Volume shows how many shares were traded in a given period. It tells you the **conviction** behind a price move.

**How to use it:**
- **Price up + high volume** = strong buying, trend likely to continue
- **Price up + low volume** = weak move, could reverse
- **Price down + high volume** = strong selling, could fall further
- **Price down + low volume** = not much panic, may bounce back
- **Volume spike** = something significant happened (news, earnings, etc.)

Think of volume as the "fuel" behind a price move. A move with high volume has more fuel and is more likely to continue.
""")

# -----------------------------------------------------------------------
# SMA
# -----------------------------------------------------------------------
st.subheader("📈 SMA — Simple Moving Average")
st.markdown("""
An SMA smooths out price data by calculating the average closing price over a set number of days.

**Common periods:**
| Period | Use case | Timeframe |
|--------|----------|-----------|
| **SMA 20** | Short-term trend | Swing trading (days to weeks) |
| **SMA 50** | Medium-term trend | Position trading (weeks to months) |
| **SMA 200** | Long-term trend | Investing (months to years) |

**How to read it:**
- **Price above SMA** = uptrend (bullish)
- **Price below SMA** = downtrend (bearish)
- **Price bouncing off SMA** = that SMA is acting as support/resistance
- **SMA flattening out** = trend is losing momentum

**Key crossover signals:**
- **Golden Cross** = 50 SMA crosses ABOVE 200 SMA → strong buy signal
- **Death Cross** = 50 SMA crosses BELOW 200 SMA → strong sell signal

These crossovers are watched by millions of traders and can become self-fulfilling prophecies.
""")

# -----------------------------------------------------------------------
# EMA
# -----------------------------------------------------------------------
st.subheader("⚡ EMA — Exponential Moving Average")
st.markdown("""
Similar to SMA but gives **more weight to recent prices**, making it react faster to price changes.

**SMA vs EMA:** If the price suddenly spikes, the EMA will move towards it faster than the SMA. This makes EMAs better for catching trends early, but they also give more false signals.

**Common periods:**
| Period | Use case |
|--------|----------|
| **EMA 9** | Very short-term, fast signals (day trading) |
| **EMA 21** | Short-term swing trading |
| **EMA 50** | Medium-term trend |

**How to use it:**
- When the **9 EMA crosses above the 21 EMA** = short-term momentum turning bullish
- When the **9 EMA crosses below the 21 EMA** = short-term momentum turning bearish
- **Price pulling back to the 21 EMA** in an uptrend can be a good entry point

**For your SIPP/ISA (long-term):** Focus on the SMA 50 and 200 — EMAs are more useful for shorter-term trading in your GIA.
""")

# -----------------------------------------------------------------------
# RSI
# -----------------------------------------------------------------------
st.subheader("🔄 RSI — Relative Strength Index")
st.markdown("""
RSI measures how fast and how much the price is changing on a scale of 0 to 100. It helps identify when a stock might be due for a reversal.

**The three zones:**

| RSI Range | Signal | What it means |
|-----------|--------|---------------|
| **70 - 100** | Overbought | Price has risen a lot, may be due for a pullback |
| **30 - 70** | Neutral | Normal trading range |
| **0 - 30** | Oversold | Price has fallen a lot, may be due for a bounce |

**How to use it:**
- RSI above 70 does NOT mean "sell immediately" — in strong uptrends, RSI can stay above 70 for weeks
- RSI below 30 does NOT mean "buy immediately" — in strong downtrends, RSI can stay below 30 for weeks
- The **best signals** come when RSI diverges from price:
  - Price makes a new high but RSI makes a lower high = **bearish divergence** (weakness)
  - Price makes a new low but RSI makes a higher low = **bullish divergence** (strength)

**Practical tip:** Look for RSI below 30 on stocks you already want to own — it could be a good entry point.
""")

# -----------------------------------------------------------------------
# MACD
# -----------------------------------------------------------------------
st.subheader("📉 MACD — Moving Average Convergence Divergence")
st.markdown("""
MACD shows the relationship between two EMAs and helps identify momentum changes. It has three components:

| Component | What it is | On the chart |
|-----------|------------|--------------|
| **MACD Line** | Fast EMA (12) minus Slow EMA (26) | Blue line |
| **Signal Line** | 9-period EMA of the MACD line | Orange line |
| **Histogram** | MACD minus Signal | Green/Red bars |

**How to read it:**
- **MACD crosses ABOVE signal line** = bullish momentum → potential buy
- **MACD crosses BELOW signal line** = bearish momentum → potential sell
- **Histogram getting taller (green)** = bullish momentum is INCREASING
- **Histogram getting shorter** = momentum is FADING (even if still green)
- **MACD above zero** = overall bullish
- **MACD below zero** = overall bearish

**The best signals** combine multiple confirmations:
- MACD crosses above signal AND histogram turns green AND price is above SMA 50 = strong buy signal

**Common mistake:** Don't use MACD alone. It's a lagging indicator (based on past data), so it works best when confirmed by other indicators like RSI and volume.
""")

# -----------------------------------------------------------------------
# Bollinger Bands
# -----------------------------------------------------------------------
st.subheader("🎯 Bollinger Bands")
st.markdown("""
Bollinger Bands create a volatility envelope around the price. They consist of three lines:

| Line | Calculation |
|------|-------------|
| **Upper Band** | 20-day SMA + 2 standard deviations |
| **Middle Band** | 20-day SMA |
| **Lower Band** | 20-day SMA - 2 standard deviations |

**How to read them:**
- **Price touches upper band** = may be overbought (but strong trends ride the upper band)
- **Price touches lower band** = may be oversold (but strong downtrends ride the lower band)
- **Bands squeezing (narrowing)** = low volatility → a big move is coming (but doesn't tell you which direction)
- **Bands expanding** = high volatility, big moves happening
- **Price bouncing between bands** = range-bound market (good for buy low / sell high)

**Practical use:**
In a sideways market, buy near the lower band and sell near the upper band. In a trending market, the bands help you identify when the trend is overstretched.
""")

# -----------------------------------------------------------------------
# Combining indicators
# -----------------------------------------------------------------------
st.subheader("🧩 Putting It All Together")
st.markdown("""
No single indicator is reliable on its own. The power comes from **combining** them:

**Example: Finding a buy opportunity**
1. Price is above the 200 SMA (long-term uptrend is intact)
2. Price pulls back to the 50 SMA (short-term dip)
3. RSI drops to 30-35 (oversold on the pullback)
4. MACD histogram starts turning green (momentum shifting back up)
5. Volume increases on the bounce (buyers stepping in)

→ This confluence of signals gives you much higher confidence than any single indicator.

**For your portfolio strategy:**

| Account | Strategy | Key indicators |
|---------|----------|----------------|
| **SIPP** | Long-term buy & hold | SMA 200, RSI (for entry timing) |
| **SS ISA** | Medium-term growth | SMA 50/200, MACD crossovers |
| **GIA (IBKR)** | Active trading | EMA 9/21, RSI, MACD, Bollinger Bands, Volume |

**Golden rules:**
- Never rely on one indicator alone
- The trend is your friend (don't fight the SMA 200)
- Volume confirms everything
- Be patient — the best setups take time to develop
""")

# -----------------------------------------------------------------------
# Common mistakes
# -----------------------------------------------------------------------
st.subheader("⚠️ Common Mistakes")
st.markdown("""
1. **Over-trading** — Seeing signals everywhere because you have too many indicators. Start with SMA + RSI, add more only when you understand those.

2. **Ignoring the bigger picture** — A stock might look oversold on the 1-month chart but is in a massive downtrend on the 1-year chart. Always check the longer timeframe first.

3. **Confirmation bias** — Only looking at indicators that support what you want to do. If you want to buy, you'll find a reason. Be honest about what ALL the indicators say.

4. **No risk management** — Even the best setup can fail. Never put more than you can afford to lose on any single trade in your GIA.

5. **Analysis paralysis** — Too many indicators on the screen = confusion. Keep it simple: trend (SMA), momentum (RSI or MACD), and volume.
""")

st.divider()
st.page_link("pages/09_charting.py", label="Back to Technical Analysis", icon="📊")
