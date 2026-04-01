"""Daily market analysis task — runs at 07:30 UTC."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from data_service import models, portfolio_calc
from agent import llm_client

logger = logging.getLogger(__name__)


def _build_portfolio_context():
    """Build a text summary of current portfolio state for the LLM."""
    lines = []
    for p in models.get_portfolios():
        summary = portfolio_calc.calculate_portfolio_summary(p["id"])
        if not summary:
            continue
        total = sum(r["market_value"] for r in summary)
        lines.append(f"\n## {p['name']} (Total: {total:,.0f})")
        for r in summary[:10]:  # top 10 by weight
            pnl_str = f"P&L: {r['pnl']:+,.0f}" if r["pnl"] is not None else ""
            lines.append(f"  {r['ticker']:10s} {r['weight']:>6.1%}  {pnl_str}")

    rm_lines = []
    for p in models.get_portfolios():
        rm = models.get_latest_risk_metrics(p["id"])
        if rm:
            rm_lines.append(
                f"  {p['name']}: Sharpe={rm['sharpe_ratio']:.2f}, "
                f"Vol={rm['volatility_annual']:.1%}, MDD={rm['max_drawdown']:.1%}, "
                f"CVaR95={rm['cvar_95']:.2%}"
            )

    macro = models.get_latest_macro()
    macro_lines = []
    for indicator, data in macro.items():
        macro_lines.append(f"  {indicator}: {data['value']:.2f} (as of {data['date']})")

    context = "# Current Portfolio State\n"
    context += "\n".join(lines)
    if rm_lines:
        context += "\n\n# Risk Metrics\n" + "\n".join(rm_lines)
    if macro_lines:
        context += "\n\n# Macro Indicators\n" + "\n".join(macro_lines)

    return context


def run():
    """Generate daily morning analysis."""
    logger.info("Running daily analysis...")

    context = _build_portfolio_context()

    messages = [
        {"role": "system", "content": llm_client.SYSTEM_PROMPT},
        {"role": "user", "content": f"""Morning briefing request.

{context}

Provide:
1. Key overnight/pre-market developments affecting these holdings
2. Any macro risks that have changed (oil, rates, geopolitics, tariffs)
3. Specific holdings to watch today and why
4. Overall portfolio risk assessment (1-2 sentences)

Keep it under 300 words."""},
    ]

    try:
        analysis = llm_client.chat(messages, temperature=0.3)
        # First line as summary
        summary = analysis.split("\n")[0][:200]
        models.insert_agent_log("daily_analysis", summary, analysis, "info")
        logger.info(f"Daily analysis complete: {summary}")
    except Exception as e:
        logger.error(f"Daily analysis failed: {e}")
        models.insert_agent_log("daily_analysis", f"Failed: {e}", str(e), "warning")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    models.init_db()
    run()
