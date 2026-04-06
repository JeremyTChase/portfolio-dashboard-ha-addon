"""SQLite data access layer for portfolio dashboard."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml

_BASE_DIR = Path(__file__).resolve().parent.parent

def _load_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        return yaml.safe_load(f)

def _db_path():
    # Allow override via env var (for Docker/HAOS deployment)
    env_path = os.environ.get("PORTFOLIO_DB_PATH")
    if env_path:
        Path(env_path).parent.mkdir(parents=True, exist_ok=True)
        return env_path
    cfg = _load_config()
    p = _BASE_DIR / cfg["database"]["path"]
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)

def init_db():
    """Create tables from schema.sql if they don't exist."""
    with get_conn() as conn:
        schema = (_BASE_DIR / "db" / "schema.sql").read_text()
        conn.executescript(schema)

@contextmanager
def get_conn():
    """Yield a WAL-mode SQLite connection."""
    conn = sqlite3.connect(_db_path())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Portfolio CRUD ---

def upsert_portfolio(portfolio_id, name):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO portfolios (id, name) VALUES (?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name",
            (portfolio_id, name),
        )

def get_portfolios():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM portfolios").fetchall()


# --- Position CRUD ---

def upsert_position(portfolio_id, ticker, shares, avg_cost=None, currency="GBP"):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO positions (portfolio_id, ticker, shares, avg_cost_basis, currency, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(portfolio_id, ticker) DO UPDATE SET "
            "shares=excluded.shares, avg_cost_basis=COALESCE(excluded.avg_cost_basis, avg_cost_basis), "
            "currency=excluded.currency, last_updated=excluded.last_updated",
            (portfolio_id, ticker, shares, avg_cost, currency, now),
        )

def delete_position(portfolio_id, ticker):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM positions WHERE portfolio_id=? AND ticker=?",
            (portfolio_id, ticker),
        )

def get_positions(portfolio_id=None):
    with get_conn() as conn:
        if portfolio_id:
            return conn.execute(
                "SELECT * FROM positions WHERE portfolio_id=?", (portfolio_id,)
            ).fetchall()
        return conn.execute("SELECT * FROM positions").fetchall()

def get_all_tickers():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT ticker FROM positions").fetchall()
        return [r["ticker"] for r in rows]


# --- Price CRUD ---

def insert_prices(records):
    """Insert price records: list of (ticker, date_str, close, currency)."""
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO prices (ticker, date, close, currency) VALUES (?, ?, ?, ?)",
            records,
        )

def get_latest_price(ticker):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT close, date FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        return dict(row) if row else None

def get_price_series(ticker, start_date=None):
    with get_conn() as conn:
        if start_date:
            rows = conn.execute(
                "SELECT date, close FROM prices WHERE ticker=? AND date>=? ORDER BY date",
                (ticker, start_date),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, close FROM prices WHERE ticker=? ORDER BY date", (ticker,)
            ).fetchall()
        return [dict(r) for r in rows]

def get_last_price_date(ticker):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) as last_date FROM prices WHERE ticker=?", (ticker,)
        ).fetchone()
        return row["last_date"] if row else None


# --- Macro indicators ---

def insert_macro(records):
    """Insert macro records: list of (indicator, date_str, value)."""
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO macro_indicators (indicator, date, value) VALUES (?, ?, ?)",
            records,
        )

def get_latest_macro():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT indicator, value, date FROM macro_indicators "
            "WHERE (indicator, date) IN "
            "(SELECT indicator, MAX(date) FROM macro_indicators GROUP BY indicator)"
        ).fetchall()
        return {r["indicator"]: {"value": r["value"], "date": r["date"]} for r in rows}


# --- Risk metrics ---

def insert_risk_metrics(portfolio_id, metrics):
    """metrics: dict with volatility_annual, sharpe_ratio, sortino_ratio, max_drawdown, cvar_95."""
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO risk_metrics (portfolio_id, calculated_at, volatility_annual, "
            "sharpe_ratio, sortino_ratio, max_drawdown, cvar_95) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (portfolio_id, now, metrics.get("volatility_annual"),
             metrics.get("sharpe_ratio"), metrics.get("sortino_ratio"),
             metrics.get("max_drawdown"), metrics.get("cvar_95")),
        )

def get_latest_risk_metrics(portfolio_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM risk_metrics WHERE portfolio_id=? ORDER BY calculated_at DESC LIMIT 1",
            (portfolio_id,),
        ).fetchone()
        return dict(row) if row else None


# --- Agent logs ---

def insert_agent_log(task_type, summary, full_analysis="", severity="info"):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO agent_logs (task_type, created_at, summary, full_analysis, severity) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_type, now, summary, full_analysis, severity),
        )

def get_agent_logs(task_type=None, limit=20):
    with get_conn() as conn:
        if task_type:
            rows = conn.execute(
                "SELECT * FROM agent_logs WHERE task_type=? ORDER BY created_at DESC LIMIT ?",
                (task_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_logs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# --- Position snapshots (historical tracking) ---

def take_position_snapshot(portfolio_id, snapshot_date=None):
    """Snapshot current positions with GBP-converted values and weights."""
    if snapshot_date is None:
        snapshot_date = datetime.utcnow().strftime("%Y-%m-%d")

    # Use portfolio_calc for correct GBP conversion
    from data_service.portfolio_calc import calculate_portfolio_summary
    summary = calculate_portfolio_summary(portfolio_id)
    if not summary:
        return None

    total = sum(r["market_value"] for r in summary)
    with get_conn() as conn:
        for r in summary:
            conn.execute(
                "INSERT OR REPLACE INTO position_snapshots "
                "(portfolio_id, snapshot_date, ticker, shares, price, market_value, weight) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (portfolio_id, snapshot_date, r["ticker"], r["shares"],
                 r["current_price"], r["market_value"], r["weight"]),
            )
    return total


def get_position_snapshots(portfolio_id, start_date=None, end_date=None):
    """Get historical position snapshots."""
    with get_conn() as conn:
        query = "SELECT * FROM position_snapshots WHERE portfolio_id=?"
        params = [portfolio_id]
        if start_date:
            query += " AND snapshot_date>=?"
            params.append(start_date)
        if end_date:
            query += " AND snapshot_date<=?"
            params.append(end_date)
        query += " ORDER BY snapshot_date, ticker"
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_portfolio_value_history(portfolio_id):
    """Get daily total portfolio value from snapshots."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT snapshot_date, SUM(market_value) as total_value "
            "FROM position_snapshots WHERE portfolio_id=? "
            "GROUP BY snapshot_date ORDER BY snapshot_date",
            (portfolio_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Risk metrics history ---

def insert_risk_metrics_history(portfolio_id, date, total_value, metrics):
    """Store risk metrics for a specific date (daily time series)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO risk_metrics_history "
            "(portfolio_id, date, total_value, volatility_annual, sharpe_ratio, "
            "sortino_ratio, max_drawdown, cvar_95) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (portfolio_id, date, total_value,
             metrics.get("volatility_annual"), metrics.get("sharpe_ratio"),
             metrics.get("sortino_ratio"), metrics.get("max_drawdown"),
             metrics.get("cvar_95")),
        )


def get_risk_metrics_history(portfolio_id, start_date=None):
    """Get risk metrics time series."""
    with get_conn() as conn:
        query = "SELECT * FROM risk_metrics_history WHERE portfolio_id=?"
        params = [portfolio_id]
        if start_date:
            query += " AND date>=?"
            params.append(start_date)
        query += " ORDER BY date"
        return [dict(r) for r in conn.execute(query, params).fetchall()]


# --- Transaction log ---

def log_transactions(portfolio_id, old_positions, new_positions):
    """Compare old vs new positions and log the differences."""
    now = datetime.utcnow().isoformat()
    old_map = {p["ticker"]: p["shares"] for p in old_positions}
    new_map = {p["ticker"]: p["shares"] for p in new_positions}
    all_tickers = set(list(old_map.keys()) + list(new_map.keys()))

    with get_conn() as conn:
        for ticker in all_tickers:
            old_shares = old_map.get(ticker, 0)
            new_shares = new_map.get(ticker, 0)
            delta = new_shares - old_shares

            if abs(delta) < 0.001:
                continue

            if old_shares == 0:
                action = "added"
            elif new_shares == 0:
                action = "removed"
            elif delta > 0:
                action = "increased"
            else:
                action = "decreased"

            conn.execute(
                "INSERT INTO transaction_log "
                "(portfolio_id, logged_at, ticker, action, shares_before, shares_after, shares_delta) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (portfolio_id, now, ticker, action, old_shares, new_shares, delta),
            )


def get_transaction_log(portfolio_id=None, limit=50):
    """Get recent transaction log entries."""
    with get_conn() as conn:
        if portfolio_id:
            rows = conn.execute(
                "SELECT * FROM transaction_log WHERE portfolio_id=? ORDER BY logged_at DESC LIMIT ?",
                (portfolio_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transaction_log ORDER BY logged_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# --- OHLCV prices ---

def insert_ohlcv(records):
    """Insert OHLCV records: list of (ticker, date_str, open, high, low, close, volume, currency, source)."""
    with get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO ohlcv_prices "
            "(ticker, date, open, high, low, close, volume, currency, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            records,
        )


def get_ohlcv(ticker, start_date=None, end_date=None):
    """Get OHLCV data for a ticker. Returns list of dicts ordered by date."""
    with get_conn() as conn:
        query = "SELECT * FROM ohlcv_prices WHERE ticker=?"
        params = [ticker]
        if start_date:
            query += " AND date>=?"
            params.append(start_date)
        if end_date:
            query += " AND date<=?"
            params.append(end_date)
        query += " ORDER BY date"
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def get_last_ohlcv_date(ticker, source=None):
    """Get the most recent OHLCV date for a ticker."""
    with get_conn() as conn:
        if source:
            row = conn.execute(
                "SELECT MAX(date) as last_date FROM ohlcv_prices WHERE ticker=? AND source=?",
                (ticker, source),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(date) as last_date FROM ohlcv_prices WHERE ticker=?", (ticker,)
            ).fetchone()
        return row["last_date"] if row else None
