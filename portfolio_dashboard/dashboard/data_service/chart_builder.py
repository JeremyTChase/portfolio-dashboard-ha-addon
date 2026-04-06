"""Build interactive plotly candlestick charts with technical overlays."""

import re

import plotly.graph_objects as go
from plotly.subplots import make_subplots


# Colour palette
_UP_COLOUR = "#26a69a"      # Green for up candles
_DOWN_COLOUR = "#ef5350"    # Red for down candles
_MA_COLOURS = [
    "#2196f3",   # Blue
    "#ff9800",   # Orange
    "#9c27b0",   # Purple
    "#4caf50",   # Green
    "#f44336",   # Red
    "#00bcd4",   # Cyan
    "#795548",   # Brown
    "#607d8b",   # Blue-grey
]
_BB_FILL = "rgba(33, 150, 243, 0.08)"
_BB_LINE = "rgba(33, 150, 243, 0.4)"


def build_candlestick_chart(df, ticker, show_volume=True, overlays=None, height=700):
    """Build a multi-panel plotly candlestick chart.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain: date, open, high, low, close.
        Indicator columns (SMA_*, EMA_*, RSI_*, MACD_*, BB*) are used
        when listed in *overlays*.
    ticker : str
        Used for chart title.
    show_volume : bool
        Show volume bars below the price chart.
    overlays : list[str] or None
        Column names from *df* to plot.  If None, plots only candles.
    height : int
        Total chart height in pixels.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    if overlays is None:
        overlays = []

    # Determine which subplots we need
    has_rsi = any(c.startswith("RSI_") for c in overlays)
    has_macd = any(c.startswith("MACD_") for c in overlays)

    rows = 1
    row_heights = [3]
    subplot_titles = [f"{ticker}"]

    if show_volume and "volume" in df.columns:
        rows += 1
        row_heights.append(1)
        subplot_titles.append("Volume")

    rsi_row = None
    if has_rsi:
        rows += 1
        row_heights.append(1)
        subplot_titles.append("RSI")
        rsi_row = rows

    macd_row = None
    if has_macd:
        rows += 1
        row_heights.append(1)
        subplot_titles.append("MACD")
        macd_row = rows

    vol_row = 2 if (show_volume and "volume" in df.columns) else None

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )

    # --- Row 1: Candlesticks ---
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            increasing_line_color=_UP_COLOUR,
            decreasing_line_color=_DOWN_COLOUR,
            increasing_fillcolor=_UP_COLOUR,
            decreasing_fillcolor=_DOWN_COLOUR,
            name="Price",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    # --- MA overlays on price chart ---
    ma_idx = 0
    for col in overlays:
        if col.startswith("SMA_") or col.startswith("EMA_"):
            colour = _MA_COLOURS[ma_idx % len(_MA_COLOURS)]
            ma_idx += 1
            fig.add_trace(
                go.Scatter(
                    x=df["date"],
                    y=df[col],
                    mode="lines",
                    name=col,
                    line=dict(width=1.2, color=colour),
                ),
                row=1,
                col=1,
            )

    # --- Bollinger Bands ---
    _add_bollinger_traces(fig, df, overlays)

    # --- Volume ---
    if vol_row and "volume" in df.columns:
        colours = [
            _UP_COLOUR if c >= o else _DOWN_COLOUR
            for c, o in zip(df["close"], df["open"])
        ]
        fig.add_trace(
            go.Bar(
                x=df["date"],
                y=df["volume"],
                marker_color=colours,
                name="Volume",
                showlegend=False,
            ),
            row=vol_row,
            col=1,
        )

    # --- RSI ---
    if rsi_row:
        _add_rsi_subplot(fig, df, overlays, rsi_row)

    # --- MACD ---
    if macd_row:
        _add_macd_subplot(fig, df, overlays, macd_row)

    # --- Layout ---
    currency_label = "GBX (pence)" if ticker.endswith(".L") else "USD"
    fig.update_layout(
        height=height,
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=60, r=20, t=60, b=30),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text=f"Price ({currency_label})", row=1, col=1)

    # Hide weekend gaps
    fig.update_xaxes(
        rangebreaks=[dict(bounds=["sat", "mon"])],
    )

    return fig


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _add_bollinger_traces(fig, df, overlays):
    """Add Bollinger Band traces to the price chart (row 1)."""
    # Find matching BB column groups
    upper_cols = [c for c in overlays if c.startswith("BBU_")]
    for ucol in upper_cols:
        tag = ucol[4:]  # e.g. "20_2.0"
        mcol = f"BBM_{tag}"
        lcol = f"BBL_{tag}"
        if mcol in df.columns and lcol in df.columns:
            # Upper band
            fig.add_trace(
                go.Scatter(
                    x=df["date"], y=df[ucol],
                    mode="lines", name=f"BB Upper ({tag})",
                    line=dict(width=1, color=_BB_LINE, dash="dot"),
                    showlegend=False,
                ),
                row=1, col=1,
            )
            # Lower band with fill
            fig.add_trace(
                go.Scatter(
                    x=df["date"], y=df[lcol],
                    mode="lines", name=f"BB Lower ({tag})",
                    line=dict(width=1, color=_BB_LINE, dash="dot"),
                    fill="tonexty",
                    fillcolor=_BB_FILL,
                    showlegend=False,
                ),
                row=1, col=1,
            )
            # Middle band
            fig.add_trace(
                go.Scatter(
                    x=df["date"], y=df[mcol],
                    mode="lines", name=f"BB Mid ({tag})",
                    line=dict(width=1, color=_BB_LINE),
                    showlegend=True,
                ),
                row=1, col=1,
            )


def _add_rsi_subplot(fig, df, overlays, row):
    """Add RSI trace with overbought/oversold lines."""
    rsi_cols = [c for c in overlays if c.startswith("RSI_")]
    for col in rsi_cols:
        fig.add_trace(
            go.Scatter(
                x=df["date"], y=df[col],
                mode="lines", name=col,
                line=dict(width=1.5, color="#9c27b0"),
            ),
            row=row, col=1,
        )

    # Overbought / oversold lines
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=row, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=row, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="grey", opacity=0.3, row=row, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=row, col=1)


def _add_macd_subplot(fig, df, overlays, row):
    """Add MACD line, signal line, and histogram."""
    # Find the MACD tag (e.g. "12_26_9")
    macd_cols = [c for c in overlays if c.startswith("MACD_") and not c.startswith("MACDs_") and not c.startswith("MACDh_")]
    for col in macd_cols:
        tag = col[5:]  # e.g. "12_26_9"
        sig_col = f"MACDs_{tag}"
        hist_col = f"MACDh_{tag}"

        # MACD line
        fig.add_trace(
            go.Scatter(
                x=df["date"], y=df[col],
                mode="lines", name="MACD",
                line=dict(width=1.5, color="#2196f3"),
            ),
            row=row, col=1,
        )

        # Signal line
        if sig_col in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df["date"], y=df[sig_col],
                    mode="lines", name="Signal",
                    line=dict(width=1.2, color="#ff9800"),
                ),
                row=row, col=1,
            )

        # Histogram
        if hist_col in df.columns:
            colours = [_UP_COLOUR if v >= 0 else _DOWN_COLOUR for v in df[hist_col]]
            fig.add_trace(
                go.Bar(
                    x=df["date"], y=df[hist_col],
                    marker_color=colours,
                    name="Histogram",
                    showlegend=False,
                ),
                row=row, col=1,
            )

    fig.update_yaxes(title_text="MACD", row=row, col=1)
    fig.add_hline(y=0, line_dash="dot", line_color="grey", opacity=0.3, row=row, col=1)
