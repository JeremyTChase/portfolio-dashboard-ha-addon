"""CLI to import Freetrade CSV exports or portfolios.json into the database."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_service import models, csv_parser, price_updater, risk_metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def import_freetrade_csv(filepath, account_id, account_name=None):
    """Import a Freetrade activity feed CSV."""
    logger.info(f"Parsing Freetrade CSV: {filepath} -> account: {account_id}")
    positions = csv_parser.parse_freetrade_csv(filepath)

    if not positions:
        logger.error("No positions found in CSV")
        return

    name = account_name or account_id.upper()
    models.upsert_portfolio(account_id, name)

    # Clear old positions and re-insert
    old = models.get_positions(account_id)
    for p in old:
        models.delete_position(account_id, p["ticker"])

    for ticker, data in positions.items():
        models.upsert_position(
            account_id, ticker, data["shares"],
            avg_cost=data["avg_cost"], currency=data["currency"]
        )
        logger.info(f"  {ticker}: {data['shares']} shares")

    # Update import date
    with models.get_conn() as conn:
        conn.execute(
            "UPDATE portfolios SET last_import_date=? WHERE id=?",
            (datetime.utcnow().isoformat(), account_id),
        )

    logger.info(f"Imported {len(positions)} positions for {account_id}")


def import_portfolios_json(filepath):
    """Import from the existing portfolios.json format."""
    logger.info(f"Parsing portfolios.json: {filepath}")
    data = csv_parser.parse_portfolios_json(filepath)

    for portfolio_id, pdata in data.items():
        models.upsert_portfolio(portfolio_id, pdata["name"])

        # Clear and re-insert
        old = models.get_positions(portfolio_id)
        for p in old:
            models.delete_position(portfolio_id, p["ticker"])

        for ticker, pos in pdata["positions"].items():
            models.upsert_position(
                portfolio_id, ticker, pos["shares"],
                avg_cost=pos["avg_cost"], currency=pos["currency"]
            )

        logger.info(f"  {portfolio_id}: {len(pdata['positions'])} positions")

    logger.info(f"Imported {len(data)} portfolios")


def main():
    parser = argparse.ArgumentParser(description="Import portfolio data")
    parser.add_argument("--file", required=True, help="CSV or JSON file to import")
    parser.add_argument("--format", choices=["csv", "json"], help="File format (auto-detected if not specified)")
    parser.add_argument("--account", help="Account ID for CSV import (e.g. sip, ss_isa)")
    parser.add_argument("--account-name", help="Display name for the account")
    parser.add_argument("--fetch-prices", action="store_true", help="Fetch prices after import")
    parser.add_argument("--calc-risk", action="store_true", help="Calculate risk metrics after import")
    args = parser.parse_args()

    models.init_db()

    filepath = Path(args.file)
    fmt = args.format or ("json" if filepath.suffix == ".json" else "csv")

    if fmt == "json":
        import_portfolios_json(str(filepath))
    elif fmt == "csv":
        if not args.account:
            parser.error("--account is required for CSV imports")
        import_freetrade_csv(str(filepath), args.account, args.account_name)

    if args.fetch_prices:
        logger.info("Fetching prices...")
        price_updater.fetch_and_store_prices()

    if args.calc_risk:
        logger.info("Calculating risk metrics...")
        for p in models.get_portfolios():
            risk_metrics.calculate_and_store_metrics(p["id"])

    logger.info("Done!")


if __name__ == "__main__":
    main()
