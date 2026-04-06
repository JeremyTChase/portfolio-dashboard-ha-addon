"""Technical analysis indicators — pure computation, no I/O.

Accepts a pandas DataFrame with OHLCV columns and returns the same
DataFrame with indicator columns appended.  Works identically whether
the data came from yfinance or IBKR.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Default indicator configuration
DEFAULT_INDICATORS = {
    "sma": [20, 50, 200],
    "ema": [9, 21],
    "rsi": {"length": 14},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bbands": {"length": 20, "std": 2.0},
}


def compute_indicators(df, indicators=None):
    """Compute technical indicators and append columns to *df*.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain at least a 'close' column.  'high', 'low', 'open'
        and 'volume' are used when available.
    indicators : dict or None
        Indicator config — see DEFAULT_INDICATORS for the schema.
        ``None`` uses the defaults.

    Returns
    -------
    pd.DataFrame
        A copy of *df* with indicator columns appended.
    """
    if indicators is None:
        indicators = DEFAULT_INDICATORS

    out = df.copy()

    if "sma" in indicators:
        out = compute_sma(out, indicators["sma"])
    if "ema" in indicators:
        out = compute_ema(out, indicators["ema"])
    if "rsi" in indicators:
        cfg = indicators["rsi"] if isinstance(indicators["rsi"], dict) else {"length": indicators["rsi"]}
        out = compute_rsi(out, **cfg)
    if "macd" in indicators:
        cfg = indicators["macd"] if isinstance(indicators["macd"], dict) else {}
        out = compute_macd(out, **cfg)
    if "bbands" in indicators:
        cfg = indicators["bbands"] if isinstance(indicators["bbands"], dict) else {}
        out = compute_bbands(out, **cfg)

    return out


# ---------------------------------------------------------------------------
# Individual indicator functions
# ---------------------------------------------------------------------------

def compute_sma(df, periods):
    """Add SMA columns (e.g. SMA_20, SMA_50, SMA_200)."""
    out = df.copy()
    close = out["close"]
    for p in periods:
        out[f"SMA_{p}"] = close.rolling(window=p, min_periods=p).mean()
    return out


def compute_ema(df, periods):
    """Add EMA columns (e.g. EMA_9, EMA_21)."""
    out = df.copy()
    close = out["close"]
    for p in periods:
        out[f"EMA_{p}"] = close.ewm(span=p, adjust=False).mean()
    return out


def compute_rsi(df, length=14):
    """Add RSI column using Wilder smoothing."""
    out = df.copy()
    delta = out["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    rs = avg_gain / avg_loss
    out[f"RSI_{length}"] = 100 - (100 / (1 + rs))
    return out


def compute_macd(df, fast=12, slow=26, signal=9):
    """Add MACD line, signal line, and histogram columns."""
    out = df.copy()
    close = out["close"]

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    tag = f"{fast}_{slow}_{signal}"
    out[f"MACD_{tag}"] = macd_line
    out[f"MACDs_{tag}"] = signal_line
    out[f"MACDh_{tag}"] = histogram
    return out


def compute_bbands(df, length=20, std=2.0):
    """Add Bollinger Bands (upper, middle, lower)."""
    out = df.copy()
    close = out["close"]

    middle = close.rolling(window=length, min_periods=length).mean()
    rolling_std = close.rolling(window=length, min_periods=length).std()

    tag = f"{length}_{std}"
    out[f"BBM_{tag}"] = middle
    out[f"BBU_{tag}"] = middle + std * rolling_std
    out[f"BBL_{tag}"] = middle - std * rolling_std
    return out


# ---------------------------------------------------------------------------
# Signal helpers
# ---------------------------------------------------------------------------

def rsi_signal(rsi_value):
    """Return human-readable RSI signal."""
    if rsi_value is None or pd.isna(rsi_value):
        return "N/A"
    if rsi_value >= 70:
        return "Overbought"
    if rsi_value <= 30:
        return "Oversold"
    return "Neutral"


def price_vs_sma(price, sma_value):
    """Return whether price is above or below SMA."""
    if price is None or sma_value is None or pd.isna(price) or pd.isna(sma_value):
        return "N/A"
    return "Above" if price >= sma_value else "Below"
