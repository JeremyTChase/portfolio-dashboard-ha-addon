#!/bin/bash
# Setup script for Raspberry Pi 5 deployment
set -e

INSTALL_DIR="${1:-/home/pi/portfolio-dashboard}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Portfolio Dashboard — Pi Setup ==="
echo "Install dir: $INSTALL_DIR"

# Copy dashboard to install dir
if [ "$REPO_DIR" != "$INSTALL_DIR" ]; then
    mkdir -p "$INSTALL_DIR"
    cp -r "$REPO_DIR"/* "$INSTALL_DIR/"
fi

cd "$INSTALL_DIR"

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Initialise database
python -c "
import sys; sys.path.insert(0, '.')
from data_service.models import init_db
init_db()
print('Database initialised')
"

# Import initial portfolio data if available
PORTFOLIO_JSON="../data/portfolios.json"
if [ -f "$PORTFOLIO_JSON" ]; then
    echo "Importing initial portfolio data..."
    python cli/import_csv.py --file "$PORTFOLIO_JSON" --format json --fetch-prices --calc-risk
fi

# Install systemd services
echo "Installing systemd services..."
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"

for svc in portfolio-data portfolio-dashboard portfolio-agent; do
    sudo tee /etc/systemd/system/$svc.service > /dev/null << EOSVC
[Unit]
Description=Portfolio $svc
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/.venv/bin:/usr/bin
Restart=on-failure
RestartSec=10
EOSVC

    case $svc in
        portfolio-data)
            sudo tee -a /etc/systemd/system/$svc.service > /dev/null << EOSVC
ExecStart=$VENV_PYTHON -m data_service.price_updater
EOSVC
            ;;
        portfolio-dashboard)
            sudo tee -a /etc/systemd/system/$svc.service > /dev/null << EOSVC
ExecStart=$INSTALL_DIR/.venv/bin/streamlit run streamlit_app/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0
EOSVC
            ;;
        portfolio-agent)
            sudo tee -a /etc/systemd/system/$svc.service > /dev/null << EOSVC
ExecStart=$VENV_PYTHON agent/runner.py
EOSVC
            ;;
    esac

    sudo tee -a /etc/systemd/system/$svc.service > /dev/null << EOSVC

[Install]
WantedBy=multi-user.target
EOSVC
done

sudo systemctl daemon-reload
sudo systemctl enable portfolio-dashboard portfolio-agent

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Start the dashboard:  sudo systemctl start portfolio-dashboard"
echo "Start the agent:      sudo systemctl start portfolio-agent"
echo "Dashboard URL:        http://$(hostname):8501"
echo ""
echo "To import new Freetrade data:"
echo "  cd $INSTALL_DIR && source .venv/bin/activate"
echo "  python cli/import_csv.py --file ~/Downloads/freetrade-export.csv --account sip --fetch-prices --calc-risk"
