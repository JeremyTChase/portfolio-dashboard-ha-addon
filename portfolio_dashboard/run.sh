#!/bin/bash
set -e

echo "=== Portfolio Dashboard Add-on Starting ==="

# Read HA add-on options
OPTIONS_FILE="/data/options.json"
if [ -f "$OPTIONS_FILE" ]; then
    export VLLM_BASE_URL=$(jq -r '.vllm_base_url' "$OPTIONS_FILE")
    export VLLM_MODEL=$(jq -r '.vllm_model' "$OPTIONS_FILE")
    export TZ=$(jq -r '.timezone' "$OPTIONS_FILE")
    export PRICE_UPDATE_INTERVAL=$(jq -r '.price_update_interval' "$OPTIONS_FILE")
    export DAILY_ANALYSIS_TIME=$(jq -r '.daily_analysis_time' "$OPTIONS_FILE")
    export WEEKLY_REVIEW_DAY=$(jq -r '.weekly_review_day' "$OPTIONS_FILE")
    export WEEKLY_REVIEW_TIME=$(jq -r '.weekly_review_time' "$OPTIONS_FILE")
    echo "Options loaded from $OPTIONS_FILE"
else
    echo "No options file found, using defaults"
fi

export PORTFOLIO_DB_PATH="/data/portfolio.db"
export PORTFOLIO_DATA_DIR="/data"

cd /app/dashboard

# Initialise database
python3 -c "
import sys; sys.path.insert(0, '.')
from data_service.models import init_db
init_db()
print('Database initialised at $PORTFOLIO_DB_PATH')
"

# Import portfolio data if portfolios.json exists and DB is empty
if [ -f "/data/portfolios.json" ]; then
    python3 -c "
import sys; sys.path.insert(0, '.')
from data_service import models
models.init_db()
if not models.get_portfolios():
    print('Importing initial portfolio data...')
    from cli.import_csv import import_portfolios_json
    import_portfolios_json('/data/portfolios.json')
    from data_service.price_updater import fetch_and_store_prices
    fetch_and_store_prices()
    from data_service.risk_metrics import calculate_and_store_metrics
    for p in models.get_portfolios():
        calculate_and_store_metrics(p['id'])
    print('Initial import complete')
else:
    print('Portfolios already loaded, skipping import')
"
fi

# Also check /config/ for portfolios.json (HA config dir)
if [ -f "/config/portfolios.json" ] && [ ! -f "/data/portfolios.json" ]; then
    cp /config/portfolios.json /data/portfolios.json
    echo "Copied portfolios.json from /config to /data"
fi

# Start agent in background
echo "Starting agent service..."
python3 agent/runner.py &
AGENT_PID=$!
echo "Agent PID: $AGENT_PID"

# Start Streamlit (foreground — keeps container alive)
echo "Starting dashboard on port 8501..."
# Bind to 0.0.0.0 but rely on password auth for protection.
# For Tailscale-only access, set DASHBOARD_BIND_ADDRESS=127.0.0.1
BIND_ADDR="${DASHBOARD_BIND_ADDRESS:-0.0.0.0}"
echo "Binding dashboard to ${BIND_ADDR}:8501"

exec streamlit run streamlit_app/app.py \
    --server.port=8501 \
    --server.headless=true \
    --server.address="${BIND_ADDR}" \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
