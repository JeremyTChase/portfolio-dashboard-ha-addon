#!/bin/bash
set -e

echo "=== Portfolio Dashboard Add-on Starting ==="

# Read HA add-on options
OPTIONS_FILE="/data/options.json"
if [ -f "$OPTIONS_FILE" ]; then
    export VLLM_BASE_URL=$(jq -r '.vllm_base_url' "$OPTIONS_FILE")
    export VLLM_MODEL=$(jq -r '.vllm_model' "$OPTIONS_FILE")
    export TZ=$(jq -r '.timezone' "$OPTIONS_FILE")
    echo "Options loaded from $OPTIONS_FILE"
else
    echo "No options file found, using defaults"
fi

# Use shared DB so NemoClaw and dashboard share the same data
export PORTFOLIO_DB_PATH="/share/portfolio-dashboard/portfolio.db"
export PORTFOLIO_DATA_DIR="/data"

mkdir -p /share/portfolio-dashboard

cd /app/dashboard

# Initialise database
python3 -c "
import sys; sys.path.insert(0, '.')
from data_service.models import init_db
init_db()
print('Database at $PORTFOLIO_DB_PATH')
"

# Migrate: if old DB exists in /data but shared one is empty, copy it
python3 -c "
import sys, os, shutil; sys.path.insert(0, '.')
from data_service import models
models.init_db()
if not models.get_portfolios() and os.path.exists('/data/portfolio.db'):
    print('Migrating DB from /data to /share...')
    shutil.copy2('/data/portfolio.db', '/share/portfolio-dashboard/portfolio.db')
    print('Migration complete')
"

# Start Streamlit only — NemoClaw handles agent tasks
echo "Starting dashboard on port 8501 (display only — NemoClaw handles agent tasks)..."
BIND_ADDR="${DASHBOARD_BIND_ADDRESS:-0.0.0.0}"
echo "Binding to ${BIND_ADDR}:8501"

exec streamlit run streamlit_app/app.py \
    --server.port=8501 \
    --server.headless=true \
    --server.address="${BIND_ADDR}" \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
