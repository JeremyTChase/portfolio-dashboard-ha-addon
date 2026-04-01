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
