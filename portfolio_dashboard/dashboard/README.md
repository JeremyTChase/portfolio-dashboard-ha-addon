# Portfolio Dashboard

Streamlit-based portfolio monitoring dashboard with AI agent, designed for Freetrade SIP and SS ISA portfolios. Runs on Raspberry Pi as a Docker container alongside Home Assistant OS.

## Architecture

```
Raspberry Pi (HAOS)                     DGX Spark (ea42)
+---------------------------+           +-------------------+
| portfolio-dashboard       |           | vLLM inference    |
| +-- Streamlit (port 8501) | -------> | port 8000         |
| +-- Price updater (cron)  |           | Qwen3-Next-80B    |
| +-- AI agent (scheduled)  |           +-------------------+
| +-- SQLite DB (/data/)    |
+---------------------------+           DGX Spark (d680)
                                        +-------------------+
                                        | RAPIDS + cuOpt    |
                                        | JupyterLab :8888  |
                                        | GPU optimization  |
                                        +-------------------+
```

## Components

### Data Service (`data_service/`)
- **models.py** — SQLite data access layer (WAL mode for concurrent reads)
- **csv_parser.py** — Freetrade activity feed CSV parser (nets BUY/SELL to positions)
- **price_updater.py** — yfinance price fetcher, runs every 15min during market hours
- **portfolio_calc.py** — Market value, P&L, weight calculations
- **risk_metrics.py** — CPU-only: volatility, Sharpe, Sortino, max drawdown, CVaR (95%)

### Streamlit Dashboard (`streamlit_app/`)
- **app.py** — Main entry with password authentication (first-run setup + forgot password)
- **01_overview.py** — Portfolio summary cards
- **02_positions.py** — Detailed positions with live P&L
- **03_allocation.py** — Pie/bar charts, geographic split
- **04_risk.py** — Risk metrics, drawdown chart, correlation heatmap
- **05_market.py** — Macro indicators (VIX, oil, gold, yields) + RSS news
- **06_agent.py** — AI agent activity log and latest analysis
- **07_import.py** — Upload Freetrade CSV to update positions

### AI Agent (`agent/`)
- **llm_client.py** — OpenAI-compatible client pointing at vLLM on DGX Spark
- **daily_analysis.py** — Morning market brief + portfolio impact (07:30 UTC)
- **price_alerts.py** — Significant move detection (>3% daily, >5% weekly)
- **weekly_review.py** — Drift detection + rebalancing suggestions (Saturday 09:00)
- **runner.py** — Scheduler entry point using `schedule` library

### CLI (`cli/`)
- **import_csv.py** — Parse Freetrade CSV or portfolios.json, update SQLite

## Security

- **Password authentication** — SHA-256 hashed, set on first login
- **Forgot password** — generates a reset token; retrieve via SSH:
  ```bash
  docker exec portfolio-dashboard cat /data/.password_reset
  ```
- **All pages** require authentication via session state
- **Password file** stored at `/data/.dashboard_password` (chmod 600)
- **No secrets in code** — vLLM URL and model passed via environment variables

## Deployment

### Prerequisites
- Raspberry Pi 4/5 with HAOS or Docker
- DGX Spark (ea42) running vLLM on port 8000 (local network: 192.168.6.241)
- Network connectivity between Pi and Spark on local network

### Build and Run

```bash
# On the Pi (SSH in)
cd /path/to/ha-addon
docker build -t portfolio-dashboard:0.2.0 .

# Run with persistent data
docker run -d \
    --name portfolio-dashboard \
    --restart unless-stopped \
    --network host \
    -e TZ=Europe/London \
    -e VLLM_BASE_URL=http://192.168.6.241:8000/v1 \
    -e VLLM_MODEL=nvidia/Qwen3-Next-80B-A3B-Instruct-NVFP4 \
    -e PORTFOLIO_DB_PATH=/data/portfolio.db \
    -e PORTFOLIO_DATA_DIR=/data \
    -v /mnt/data/portfolio-dashboard:/data \
    portfolio-dashboard:0.2.0
```

### First Run
1. Open `http://<pi-ip>:8501` in a browser
2. Set a password on the setup screen
3. Navigate to the **Import** page
4. Upload your Freetrade CSV exports (one per account)

### Import Portfolio Data via CLI

```bash
# From portfolios.json (initial seed)
docker cp portfolios.json portfolio-dashboard:/data/portfolios.json
docker exec -e PORTFOLIO_DB_PATH=/data/portfolio.db portfolio-dashboard \
    python3 -c "
import sys; sys.path.insert(0, '/app/dashboard')
from data_service import models
from cli.import_csv import import_portfolios_json
from data_service.price_updater import fetch_and_store_prices
from data_service.risk_metrics import calculate_and_store_metrics
models.init_db()
import_portfolios_json('/data/portfolios.json')
fetch_and_store_prices()
for p in models.get_portfolios():
    calculate_and_store_metrics(p['id'])
"
```

### Update Image

```bash
# After code changes
docker stop portfolio-dashboard
docker rm portfolio-dashboard
cd /path/to/ha-addon
docker build -t portfolio-dashboard:0.3.0 .
# Re-run with same -v mount to keep data
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_BASE_URL` | (required) | vLLM OpenAI-compatible endpoint |
| `VLLM_MODEL` | (required) | Model name served by vLLM |
| `PORTFOLIO_DB_PATH` | `/data/portfolio.db` | SQLite database path |
| `PORTFOLIO_DATA_DIR` | `/data` | Persistent data directory |
| `TZ` | `UTC` | Timezone for scheduling |
| `PRICE_UPDATE_INTERVAL` | `15` | Minutes between price fetches |
| `DAILY_ANALYSIS_TIME` | `07:30` | Daily AI analysis time (UTC) |
| `WEEKLY_REVIEW_DAY` | `saturday` | Weekly review day |
| `WEEKLY_REVIEW_TIME` | `09:00` | Weekly review time (UTC) |
| `DASHBOARD_BIND_ADDRESS` | `0.0.0.0` | Bind address (set `127.0.0.1` for localhost-only) |

## GPU Optimization (DGX Spark)

The portfolio optimization notebooks run on DGX Spark, not the Pi:
- **spark-d680** — RAPIDS container with cuOpt for Mean-CVaR optimization
- Access JupyterLab at `http://spark-d680:8888`
- Run `my_portfolios_v2.ipynb` with the "Portfolio Optimization" kernel
- Uses GPU-accelerated KDE scenario generation (10,000 scenarios) and cuOpt LP solver

## Freetrade CSV Format

Export from Freetrade app: Activity tab > Calendar icon > Download CSV.
The parser reads `Type=ORDER` rows, nets BUY/SELL quantities per ticker, and maps Freetrade tickers to Yahoo Finance format:
- UK stocks: `BARC` -> `BARC.L`, `RR.` -> `RR.L`
- US stocks: `NVDA` -> `NVDA`, `TSLA` -> `TSLA`
- ETFs: `ISF` -> `ISF.L`, `IUSA` -> `IUSA.L`

## Persistent Data

All data is stored in `/data/` (mounted as a Docker volume):
- `portfolio.db` — SQLite database (positions, prices, risk metrics, agent logs)
- `portfolios.json` — Initial portfolio seed file
- `.dashboard_password` — Hashed password (SHA-256)
- `.password_reset` — Temporary reset token (deleted after use)
