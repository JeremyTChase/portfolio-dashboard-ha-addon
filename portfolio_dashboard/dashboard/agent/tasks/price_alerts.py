"""Price alert task — checks for significant moves every 15 minutes."""

import logging
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_service import models
from agent import llm_client

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent

def _load_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        return yaml.safe_load(f)


def run():
    """Check each position for significant price moves."""
    cfg = _load_config()
    daily_threshold = cfg["agent"]["price_alert_threshold_daily"]
    weekly_threshold = cfg["agent"]["price_alert_threshold_weekly"]

    alerts = []

    for pos in models.get_positions():
        ticker = pos["ticker"]
        prices = models.get_price_series(ticker)
        if len(prices) < 6:
            continue

        closes = [p["close"] for p in prices]
        current = closes[-1]
        prev_day = closes[-2] if len(closes) >= 2 else current
        prev_week = closes[-6] if len(closes) >= 6 else current

        daily_change = (current - prev_day) / prev_day if prev_day else 0
        weekly_change = (current - prev_week) / prev_week if prev_week else 0

        if abs(daily_change) >= daily_threshold:
            direction = "up" if daily_change > 0 else "down"
            alerts.append({
                "ticker": ticker,
                "type": "daily",
                "change": daily_change,
                "msg": f"{ticker} moved {daily_change:+.1%} today ({direction})",
            })

        if abs(weekly_change) >= weekly_threshold:
            direction = "up" if weekly_change > 0 else "down"
            alerts.append({
                "ticker": ticker,
                "type": "weekly",
                "change": weekly_change,
                "msg": f"{ticker} moved {weekly_change:+.1%} this week ({direction})",
            })

    if not alerts:
        logger.info("No significant price moves detected")
        return

    # Get LLM to assess significance
    alert_text = "\n".join(f"- {a['msg']}" for a in alerts)

    messages = [
        {"role": "system", "content": llm_client.SYSTEM_PROMPT},
        {"role": "user", "content": f"""Price alert: significant moves detected.

{alert_text}

For each alert, briefly explain:
1. Likely cause (if obvious from recent news/macro)
2. Whether this is concerning or expected
3. Any action to consider

Keep each assessment to 1-2 sentences."""},
    ]

    try:
        analysis = llm_client.chat(messages, temperature=0.3, max_tokens=1000)
        severity = "alert" if any(abs(a["change"]) >= 0.05 for a in alerts) else "warning"
        summary = f"{len(alerts)} alert(s): " + "; ".join(a["msg"] for a in alerts[:3])
        models.insert_agent_log("price_alert", summary[:200], analysis, severity)
        logger.info(f"Price alerts logged: {summary}")
    except Exception as e:
        logger.error(f"Price alert LLM call failed: {e}")
        summary = "; ".join(a["msg"] for a in alerts[:3])
        models.insert_agent_log("price_alert", summary[:200], alert_text, "warning")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    models.init_db()
    run()
