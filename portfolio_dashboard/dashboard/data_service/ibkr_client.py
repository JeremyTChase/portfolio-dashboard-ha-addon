"""Thread-safe Interactive Brokers client wrapper.

Uses ib_async (successor to ib_insync) with a dedicated background
event-loop thread so it works safely inside Streamlit.

If ib_async is not installed, the module degrades gracefully —
``IB_AVAILABLE`` is ``False`` and ``IBKRClient`` methods return
empty results.
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional import — ib_async is optional
# ---------------------------------------------------------------------------
IB_AVAILABLE = False
try:
    from ib_async import IB, Stock, MarketOrder, LimitOrder, util
    IB_AVAILABLE = True
except ImportError:
    try:
        from ib_insync import IB, Stock, MarketOrder, LimitOrder, util
        IB_AVAILABLE = True
    except ImportError:
        logger.info("Neither ib_async nor ib_insync installed — IBKR features disabled")

_BASE_DIR = Path(__file__).resolve().parent.parent


def _load_ibkr_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("ibkr", {})


# ---------------------------------------------------------------------------
# Ticker mapping: dashboard format <-> IBKR contract
# ---------------------------------------------------------------------------

def _make_contract(ticker):
    """Convert a dashboard ticker string to an IBKR Stock contract.

    Examples
    --------
    >>> _make_contract("AAPL")        # -> Stock('AAPL', 'SMART', 'USD')
    >>> _make_contract("BARC.L")      # -> Stock('BARC', 'LSE', 'GBP')
    """
    if not IB_AVAILABLE:
        return None
    if ticker.endswith(".L"):
        symbol = ticker[:-2]
        return Stock(symbol, "LSE", "GBP")
    return Stock(ticker, "SMART", "USD")


def _ibkr_ticker_to_dashboard(contract):
    """Convert an IBKR contract back to dashboard ticker format."""
    if hasattr(contract, "exchange") and contract.exchange == "LSE":
        return f"{contract.symbol}.L"
    return contract.symbol


# Period string -> IBKR duration + bar size
_PERIOD_MAP = {
    "1M": ("1 M", "1 day"),
    "3M": ("3 M", "1 day"),
    "6M": ("6 M", "1 day"),
    "1Y": ("1 Y", "1 day"),
    "2Y": ("2 Y", "1 day"),
    "5Y": ("5 Y", "1 day"),
}


class IBKRClient:
    """Thread-safe IBKR client for use inside Streamlit."""

    def __init__(self):
        self.config = _load_ibkr_config()
        self._ib = None
        self._loop = None
        self._thread = None

        if IB_AVAILABLE:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, daemon=True
            )
            self._thread.start()
            self._ib = IB()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self):
        """Connect to TWS/Gateway. Returns True on success."""
        if not IB_AVAILABLE or self._ib is None:
            logger.error("ib_async/ib_insync not available")
            return False

        if self._ib.isConnected():
            return True

        host = self.config.get("host", "127.0.0.1")
        port = self.config.get("port", 7497)
        client_id = self.config.get("client_id", 1)
        timeout = self.config.get("timeout", 10)

        try:
            future = asyncio.run_coroutine_threadsafe(
                self._ib.connectAsync(host, port, clientId=client_id),
                self._loop,
            )
            future.result(timeout=timeout)
            logger.info(f"Connected to IBKR at {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"IBKR connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from TWS/Gateway."""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            logger.info("Disconnected from IBKR")

    def is_connected(self):
        """Check if currently connected."""
        return self._ib is not None and self._ib.isConnected()

    def _run_sync(self, coro, timeout=30):
        """Run an async coroutine on the background loop, blocking."""
        if not self.is_connected():
            return None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_historical_ohlcv(self, ticker, period="1Y"):
        """Fetch historical OHLCV bars from IBKR.

        Returns a DataFrame with columns:
        date, open, high, low, close, volume
        """
        if not self.is_connected():
            return pd.DataFrame()

        contract = _make_contract(ticker)
        if contract is None:
            return pd.DataFrame()

        duration, bar_size = _PERIOD_MAP.get(period.upper(), ("1 Y", "1 day"))

        try:
            # Qualify the contract first
            self._run_sync(self._qualify(contract))

            bars = self._run_sync(
                self._ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime="",
                    durationStr=duration,
                    barSizeSetting=bar_size,
                    whatToShow="TRADES",
                    useRTH=True,
                    formatDate=1,
                )
            )

            if not bars:
                return pd.DataFrame()

            df = util.df(bars)
            df = df.rename(columns={"date": "date"})

            # Normalise column names
            col_map = {}
            for c in df.columns:
                cl = c.lower()
                if cl in ("open", "high", "low", "close", "volume", "date"):
                    col_map[c] = cl
            df = df.rename(columns=col_map)

            # Ensure date is string
            if "date" in df.columns:
                df["date"] = df["date"].astype(str).str[:10]

            return df[["date", "open", "high", "low", "close", "volume"]]

        except Exception as e:
            logger.error(f"IBKR historical data failed for {ticker}: {e}")
            return pd.DataFrame()

    async def _qualify(self, contract):
        """Qualify a contract (fill in missing details)."""
        await self._ib.qualifyContractsAsync(contract)

    def get_realtime_quote(self, ticker):
        """Get a real-time quote snapshot.

        Returns dict with: last, bid, ask, high, low, volume, time
        """
        if not self.is_connected():
            return None

        contract = _make_contract(ticker)
        if contract is None:
            return None

        try:
            self._run_sync(self._qualify(contract))

            # Request snapshot (frozen data for paper trading)
            tickers = self._run_sync(
                self._ib.reqTickersAsync(contract)
            )

            if not tickers:
                return None

            t = tickers[0] if isinstance(tickers, list) else tickers
            return {
                "last": t.last if hasattr(t, "last") else None,
                "bid": t.bid if hasattr(t, "bid") else None,
                "ask": t.ask if hasattr(t, "ask") else None,
                "high": t.high if hasattr(t, "high") else None,
                "low": t.low if hasattr(t, "low") else None,
                "volume": t.volume if hasattr(t, "volume") else None,
                "time": str(t.time) if hasattr(t, "time") else None,
            }
        except Exception as e:
            logger.error(f"IBKR quote failed for {ticker}: {e}")
            return None

    # ------------------------------------------------------------------
    # Account & positions
    # ------------------------------------------------------------------

    def get_positions(self):
        """Get all positions in the account.

        Returns list of dicts: {ticker, shares, avg_cost, market_value, currency}
        """
        if not self.is_connected():
            return []

        try:
            positions = self._run_sync(self._ib.reqPositionsAsync())
            if not positions:
                # Try synchronous fallback
                positions = self._ib.positions()

            result = []
            for pos in positions:
                ticker = _ibkr_ticker_to_dashboard(pos.contract)
                result.append({
                    "ticker": ticker,
                    "shares": pos.position,
                    "avg_cost": pos.avgCost,
                    "market_value": pos.position * pos.avgCost,
                    "currency": pos.contract.currency,
                })
            return result
        except Exception as e:
            logger.error(f"IBKR positions fetch failed: {e}")
            return []

    def get_account_summary(self):
        """Get account summary (cash, portfolio value, etc.).

        Returns dict with key account metrics.
        """
        if not self.is_connected():
            return {}

        try:
            summary = self._run_sync(
                self._ib.reqAccountSummaryAsync()
            )
            if not summary:
                return {}

            result = {}
            for item in summary:
                result[item.tag] = {
                    "value": item.value,
                    "currency": item.currency,
                }
            return result
        except Exception as e:
            logger.error(f"IBKR account summary failed: {e}")
            return {}

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def _verify_account(self):
        """Safety check: verify connected account matches config."""
        expected = self.config.get("account_id")
        if not expected:
            return True  # No check configured

        accounts = self._ib.managedAccounts()
        if expected not in accounts:
            logger.error(
                f"Account mismatch! Expected {expected}, got {accounts}. "
                "Refusing to place order."
            )
            return False
        return True

    def place_market_order(self, ticker, action, quantity):
        """Place a market order.

        Parameters
        ----------
        ticker : str  — e.g. "AAPL" or "BARC.L"
        action : str  — "BUY" or "SELL"
        quantity : float

        Returns
        -------
        dict or None — trade info on success
        """
        if not self.is_connected():
            return None

        if not self._verify_account():
            return None

        contract = _make_contract(ticker)
        self._run_sync(self._qualify(contract))

        order = MarketOrder(action.upper(), quantity)
        trade = self._ib.placeOrder(contract, order)

        return {
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
        }

    def place_limit_order(self, ticker, action, quantity, limit_price):
        """Place a limit order.

        Parameters
        ----------
        ticker : str
        action : str  — "BUY" or "SELL"
        quantity : float
        limit_price : float

        Returns
        -------
        dict or None
        """
        if not self.is_connected():
            return None

        if not self._verify_account():
            return None

        contract = _make_contract(ticker)
        self._run_sync(self._qualify(contract))

        order = LimitOrder(action.upper(), quantity, limit_price)
        trade = self._ib.placeOrder(contract, order)

        return {
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
            "ticker": ticker,
            "action": action,
            "quantity": quantity,
            "limit_price": limit_price,
        }

    def get_open_orders(self):
        """Get all open orders."""
        if not self.is_connected():
            return []

        try:
            trades = self._ib.openTrades()
            result = []
            for t in trades:
                result.append({
                    "order_id": t.order.orderId,
                    "ticker": _ibkr_ticker_to_dashboard(t.contract),
                    "action": t.order.action,
                    "quantity": t.order.totalQuantity,
                    "order_type": t.order.orderType,
                    "status": t.orderStatus.status,
                    "limit_price": getattr(t.order, "lmtPrice", None),
                })
            return result
        except Exception as e:
            logger.error(f"IBKR open orders fetch failed: {e}")
            return []
