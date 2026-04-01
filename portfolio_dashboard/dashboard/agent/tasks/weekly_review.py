"""Weekly portfolio review task — runs Saturday morning."""

import logging
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_service import models, portfolio_calc, risk_metrics as rm_module
from agent import llm_client

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent

def _load_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        return yaml.safe_load(f)


def run():
    """Generate weekly portfolio review with rebalancing suggestions."""
    logger.info("Running weekly review...")

    portfolio_sections = []

    for p in models.get_portfolios():
        pid = p["id"]
        summary = portfolio_calc.calculate_portfolio_summary(pid)
        if not summary:
            continue

        # Recalculate risk metrics
        metrics = rm_module.calculate_and_store_metrics(pid)

        total = sum(r["market_value"] for r in summary)
        top_5 = summary[:5]

        section = f"## {p['name']} (Total: {total:,.0f})\n"
        section += "Top holdings:\n"
        for r in top_5:
            section += f"  {r['ticker']:10s} {r['weight']:>6.1%}\n"

        if metrics:
            section += f"\nRisk: Sharpe={metrics['sharpe_ratio']:.2f}, "
            section += f"Vol={metrics['volatility_annual']:.1%}, "
            section += f"MDD={metrics['max_drawdown']:.1%}, "
            section += f"CVaR95={metrics['cvar_95']:.2%}\n"

        # Concentration check (HHI)
        weights = [r["weight"] for r in summary]
        hhi = sum(w**2 for w in weights)
        section += f"\nConcentration (HHI): {hhi:.4f}"
        if hhi > 0.25:
            section += " -- HIGH concentration risk"
        section += "\n"

        portfolio_sections.append(section)

    # Macro context
    macro = models.get_latest_macro()
    macro_text = "## Macro Indicators\n"
    for indicator, data in macro.items():
        macro_text += f"  {indicator}: {data['value']:.2f}\n"

    context = "\n".join(portfolio_sections) + "\n" + macro_text

    messages = [
        {"role": "system", "content": llm_client.SYSTEM_PROMPT},
        {"role": "user", "content": f"""Weekly portfolio review.

{context}

Provide:
1. **Week in review**: How did the portfolios perform? Key movers up/down.
2. **Risk assessment**: Are concentration levels, drawdowns, or correlations concerning?
3. **Macro outlook**: What's the forward view on the key risk factors (oil/Middle East, tariffs, UK rates, defence spending)?
4. **Rebalancing suggestions**: Based on current allocations and risk metrics, should Jeremy consider any trades? Be specific about what to trim/add and why.
5. **Watchlist**: Any holdings that need close monitoring next week?

Keep it under 500 words. Be specific and actionable."""},
    ]

    try:
        analysis = llm_client.chat(messages, temperature=0.3, max_tokens=2000)
        summary = analysis.split("\n")[0][:200]
        models.insert_agent_log("weekly_review", summary, analysis, "info")
        logger.info(f"Weekly review complete: {summary}")
    except Exception as e:
        logger.error(f"Weekly review failed: {e}")
        models.insert_agent_log("weekly_review", f"Failed: {e}", str(e), "warning")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    models.init_db()
    run()
