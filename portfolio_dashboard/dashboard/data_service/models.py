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
