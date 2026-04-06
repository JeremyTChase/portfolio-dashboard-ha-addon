PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,          -- 'sip' or 'ss_isa'
    name TEXT NOT NULL,
    last_import_date TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
    ticker TEXT NOT NULL,
    shares REAL NOT NULL,
    avg_cost_basis REAL,          -- average buy price (native currency)
    currency TEXT DEFAULT 'GBP',
    last_updated TEXT,
    PRIMARY KEY (portfolio_id, ticker)
);

CREATE TABLE IF NOT EXISTS prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL NOT NULL,
    currency TEXT DEFAULT 'GBP',
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS risk_metrics (
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
    calculated_at TEXT NOT NULL,
    volatility_annual REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    max_drawdown REAL,
    cvar_95 REAL,
    PRIMARY KEY (portfolio_id, calculated_at)
);

CREATE TABLE IF NOT EXISTS macro_indicators (
    indicator TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (indicator, date)
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,       -- 'daily_analysis', 'price_alert', 'weekly_review'
    created_at TEXT NOT NULL,
    summary TEXT,
    full_analysis TEXT,
    severity TEXT DEFAULT 'info'   -- 'info', 'warning', 'alert'
);

-- Historical tracking tables

CREATE TABLE IF NOT EXISTS position_snapshots (
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
    snapshot_date TEXT NOT NULL,     -- YYYY-MM-DD
    ticker TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL,                      -- closing price on that date
    market_value REAL,
    weight REAL,                     -- portfolio weight on that date
    PRIMARY KEY (portfolio_id, snapshot_date, ticker)
);

CREATE TABLE IF NOT EXISTS risk_metrics_history (
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
    date TEXT NOT NULL,              -- YYYY-MM-DD
    total_value REAL,
    volatility_annual REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    max_drawdown REAL,
    cvar_95 REAL,
    PRIMARY KEY (portfolio_id, date)
);

CREATE TABLE IF NOT EXISTS transaction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id),
    logged_at TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,            -- 'added', 'removed', 'increased', 'decreased'
    shares_before REAL,
    shares_after REAL,
    shares_delta REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ohlcv_prices (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER,
    currency TEXT DEFAULT 'USD',
    source TEXT DEFAULT 'yfinance',  -- 'yfinance' or 'ibkr'
    PRIMARY KEY (ticker, date)
);
