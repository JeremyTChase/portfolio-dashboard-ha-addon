"""CPU-only risk metrics, ported from cufolio/backtest.py."""

import logging

import numpy as np
import pandas as pd

from . import models

logger = logging.getLogger(__name__)


def _get_returns_df(tickers, lookback_days=504):
    """Build a returns DataFrame from stored prices (last ~2 years)."""
    all_series = {}
    for ticker in tickers:
        prices = models.get_price_series(ticker)
        if not prices:
            continue
        s = pd.Series(
            {p["date"]: p["close"] for p in prices}, name=ticker, dtype=float
        )
        all_series[ticker] = s

    if not all_series:
        return pd.DataFrame()

    df = pd.DataFrame(all_series).sort_index().tail(lookback_days)
    df = df.ffill().dropna(axis=1, how="all")
    # Log returns
    returns = np.log(df / df.shift(1)).dropna()
    return returns


def sharpe_ratio(returns, risk_free=0.0):
    """Annualised Sharpe ratio. Mirrors backtest.py:564."""
    excess = returns - risk_free / 252
    mean_excess = np.mean(excess)
    std_excess = np.std(excess)
    if std_excess == 0:
        return 0.0
    return float(mean_excess / std_excess * np.sqrt(252))


def sortino_ratio(returns, risk_free=0.0):
    """Annualised Sortino ratio. Mirrors backtest.py:584."""
    excess = returns - risk_free / 252
    mean_excess = np.mean(excess)
    downside = excess[excess < 0]
    downside_dev = np.std(downside)
    if downside_dev == 0:
        return 0.0
    return float(mean_excess / downside_dev * np.sqrt(252))


def max_drawdown(returns):
    """Maximum drawdown from returns. Mirrors backtest.py:606."""
    cumulative = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (running_max - cumulative) / running_max
    return float(np.max(drawdown)) if len(drawdown) > 0 else 0.0


def cvar_95(returns):
    """Historical CVaR at 95% confidence (mean of worst 5%)."""
    sorted_returns = np.sort(returns)
    n = max(1, int(len(sorted_returns) * 0.05))
    return float(-np.mean(sorted_returns[:n]))


def calculate_and_store_metrics(portfolio_id):
    """Calculate all risk metrics for a portfolio and store in DB."""
    positions = models.get_positions(portfolio_id)
    if not positions:
        return

    tickers = [p["ticker"] for p in positions]
    returns_df = _get_returns_df(tickers)
    if returns_df.empty:
        logger.warning(f"No returns data for {portfolio_id}")
        return

    # Calculate portfolio weights from current market values
    from . import portfolio_calc
    summary = portfolio_calc.calculate_portfolio_summary(portfolio_id)
    weights = {}
    for row in summary:
        if row["ticker"] in returns_df.columns:
            weights[row["ticker"]] = row["weight"]

    # Normalize weights to available tickers
    available = [t for t in returns_df.columns if t in weights]
    if not available:
        return

    w = np.array([weights.get(t, 0) for t in available])
    w = w / w.sum()  # renormalize

    # Portfolio returns (weighted)
    portfolio_returns = (returns_df[available].values @ w)

    metrics = {
        "volatility_annual": float(np.std(portfolio_returns) * np.sqrt(252)),
        "sharpe_ratio": sharpe_ratio(portfolio_returns),
        "sortino_ratio": sortino_ratio(portfolio_returns),
        "max_drawdown": max_drawdown(portfolio_returns),
        "cvar_95": cvar_95(portfolio_returns),
    }

    models.insert_risk_metrics(portfolio_id, metrics)
    logger.info(f"Updated risk metrics for {portfolio_id}: {metrics}")
    return metrics
