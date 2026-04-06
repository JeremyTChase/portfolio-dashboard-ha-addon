"""Sync IBKR positions to the GIA portfolio in the local database."""

import logging
from datetime import datetime

from . import models

logger = logging.getLogger(__name__)

GIA_PORTFOLIO_ID = "gia"


def sync_positions(ibkr_client):
    """Pull positions from IBKR and sync to the GIA portfolio.

    1. Fetches current IBKR positions
    2. Compares with existing GIA positions in DB
    3. Logs transaction differences
    4. Upserts new positions, removes closed ones

    Returns
    -------
    dict — summary of changes: {added, removed, updated, unchanged, total}
    """
    if not ibkr_client or not ibkr_client.is_connected():
        logger.error("IBKR not connected — cannot sync positions")
        return None

    # Ensure GIA portfolio exists
    models.upsert_portfolio(GIA_PORTFOLIO_ID, "GIA (IBKR)")

    # Get current DB positions
    old_positions = models.get_positions(GIA_PORTFOLIO_ID)
    old_map = {p["ticker"]: p["shares"] for p in old_positions}

    # Get IBKR positions
    ibkr_positions = ibkr_client.get_positions()
    new_map = {p["ticker"]: p["shares"] for p in ibkr_positions if p["shares"] != 0}

    # Log transactions
    models.log_transactions(
        GIA_PORTFOLIO_ID,
        old_positions,
        [{"ticker": t, "shares": s} for t, s in new_map.items()],
    )

    # Apply changes
    added = 0
    removed = 0
    updated = 0
    unchanged = 0

    # Upsert IBKR positions
    for ticker, shares in new_map.items():
        ibkr_pos = next((p for p in ibkr_positions if p["ticker"] == ticker), {})
        avg_cost = ibkr_pos.get("avg_cost")
        currency = ibkr_pos.get("currency", "USD")

        if ticker not in old_map:
            added += 1
        elif abs(old_map[ticker] - shares) > 0.001:
            updated += 1
        else:
            unchanged += 1

        models.upsert_position(
            GIA_PORTFOLIO_ID, ticker, shares,
            avg_cost=avg_cost, currency=currency,
        )

    # Remove positions that no longer exist in IBKR
    for ticker in old_map:
        if ticker not in new_map:
            models.delete_position(GIA_PORTFOLIO_ID, ticker)
            removed += 1

    total = len(new_map)
    logger.info(
        f"IBKR sync complete: {total} positions "
        f"(+{added} new, ~{updated} updated, -{removed} removed, ={unchanged} unchanged)"
    )

    return {
        "added": added,
        "removed": removed,
        "updated": updated,
        "unchanged": unchanged,
        "total": total,
    }
