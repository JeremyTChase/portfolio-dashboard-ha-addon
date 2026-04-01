"""Agent service entry point — runs scheduled tasks via the schedule library."""

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import schedule
import yaml

from data_service import models, price_updater

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("agent")

_BASE_DIR = Path(__file__).resolve().parent.parent

def _load_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        return yaml.safe_load(f)


def run_daily_analysis():
    from agent.tasks import daily_analysis
    daily_analysis.run()


def run_price_alerts():
    if price_updater.is_market_hours():
        from agent.tasks import price_alerts
        price_alerts.run()


def run_weekly_review():
    from agent.tasks import weekly_review
    weekly_review.run()


def run_price_update():
    if price_updater.is_market_hours():
        price_updater.fetch_and_store_prices()


def run_daily_snapshot():
    """Take a daily snapshot of all portfolios — positions, values, and risk metrics."""
    from data_service import risk_metrics
    today = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d")
    for p in models.get_portfolios():
        total = models.take_position_snapshot(p["id"], today)
        m = risk_metrics.calculate_and_store_metrics(p["id"])
        if total and m:
            models.insert_risk_metrics_history(p["id"], today, total, m)
    logger.info(f"Daily snapshot taken for {today}")


def main():
    models.init_db()
    cfg = _load_config()

    agent_cfg = cfg["agent"]
    price_cfg = cfg["price_update"]

    # Allow env var overrides (from HA add-on options)
    daily_time = os.environ.get("DAILY_ANALYSIS_TIME", agent_cfg["daily_analysis_time"])
    interval = int(os.environ.get("PRICE_UPDATE_INTERVAL", price_cfg["interval_minutes"]))
    day = os.environ.get("WEEKLY_REVIEW_DAY", agent_cfg["weekly_review_day"])
    time_str = os.environ.get("WEEKLY_REVIEW_TIME", agent_cfg["weekly_review_time"])

    # Schedule tasks
    schedule.every().day.at(daily_time).do(run_daily_analysis)
    schedule.every().day.at("21:05").do(run_daily_snapshot)  # After markets close
    schedule.every(interval).minutes.do(run_price_update)
    schedule.every(interval).minutes.do(run_price_alerts)
    getattr(schedule.every(), day).at(time_str).do(run_weekly_review)

    logger.info("Agent service started. Scheduled tasks:")
    logger.info(f"  Daily analysis: {daily_time} UTC")
    logger.info(f"  Daily snapshot: 21:05 UTC (after market close)")
    logger.info(f"  Price updates: every {interval}min (market hours)")
    logger.info(f"  Price alerts: every {interval}min (market hours)")
    logger.info(f"  Weekly review: {day} {time_str} UTC")

    # Run initial price fetch and snapshot
    logger.info("Running initial price fetch...")
    price_updater.fetch_and_store_prices()
    run_daily_snapshot()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
