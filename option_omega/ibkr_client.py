"""
ibkr_client.py
==============
Thread-safe IBKR TWS/Gateway wrapper built on ibapi.

Subscriptions (set up once at startup by DataPuller)
----------------------------------------------------
  subscribe_live(symbol, callback) — reqMktData for STK or INDEX
  VIX / VIX9D use secType="IND", exchange="CBOE"

Historical data (blocking, called on startup or for daily closes)
-----------------------------------------------------------------
  get_historical_daily_closes(symbol, n_days) → list[DailyClose]
    uses whatToShow="TRADES", barSizeSetting="1 day", useRTH=False
    so the 4:15 PM settlement price is captured as the day close.

Option helpers (called only at order time — never in the hot loop)
-----------------------------------------------------------------
  get_option_contract()    — reqContractDetails to resolve strike
  get_option_price()       — returns mid of best bid/ask
  get_bid() / get_ask()    — individual bid/ask for spread checks
  place_limit_order()      — places and waits up to 30 s for fill
  place_market_order()     — places MOC / MKT order
  get_account_nlv()        — reqAccountSummary for NLV field
"""

import threading
import time
from datetime import datetime, date, timedelta
from typing   import Optional, Callable

from ibapi.client   import EClient
from ibapi.wrapper  import EWrapper
from ibapi.contract import Contract
from ibapi.order    import Order
from ibapi.common   import BarData

from data_store import DailyClose


# ── EWrapper + EClient combined ───────────────────────────────────────────────
class _IBKRWrapper(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)


class IBKRClient:

    # Tick types used throughout
    TICK_BID   = 1
    TICK_ASK   = 2
    TICK_LAST  = 4
    TICK_CLOSE = 9

    def __init__(self, host: str = "127.0.0.1",
                 port: int = 7497, client_id: int = 1):
        self._host      = host
        self._port      = port
        self._client_id = client_id

        self._app       = _IBKRWrapper()
        self._lock      = threading.RLock()
        self._next_id   = 1
        self._connected = False

        # Live tick state: reqId → {bid, ask, last}
        self._live_ticks: dict = {}
        # reqId → symbol mapping for dispatch
        self._req_symbol: dict = {}
        # symbol → list of registered callbacks
        self._callbacks: dict  = {}

        # Blocking result events
        self._hist_bars:    list               = []
        self._hist_event    = threading.Event()
        self._order_fills:  dict               = {}
        self._order_events: dict               = {}
        self._nlv:          Optional[float]    = None
        self._nlv_event     = threading.Event()
        self._contract_details: list           = []
        self._contract_event  = threading.Event()

        # Wire callbacks into the wrapper
        self._wire_callbacks()

    # ── Connection ────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        self._app.connect(self._host, self._port, self._client_id)
        t = threading.Thread(target=self._app.run,
                             name="ibkr_reader", daemon=True)
        t.start()
        for _ in range(50):
            if self._connected:
                return True
            time.sleep(0.1)
        print("[IBKRClient] Connection timeout")
        return False

    def disconnect(self):
        self._app.disconnect()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ── Callback wiring ───────────────────────────────────────────────────────
    def _wire_callbacks(self):

        client = self

        def nextValidId(orderId: int):
            client._next_id  = orderId
            client._connected = True
            client._app.reqMarketDataType(1)   # 1=live, 3=delayed, 4=delayed frozen

        def tickPrice(reqId: int, tickType: int, price: float, attrib):
            with client._lock:
                if reqId not in client._live_ticks:
                    client._live_ticks[reqId] = {}
                if tickType == client.TICK_BID:
                    client._live_ticks[reqId]["bid"] = price
                elif tickType == client.TICK_ASK:
                    client._live_ticks[reqId]["ask"] = price
                elif tickType == client.TICK_LAST:
                    client._live_ticks[reqId]["last"] = price
                    symbol = client._req_symbol.get(reqId)
                    if symbol and symbol in client._callbacks:
                        for cb in client._callbacks[symbol]:
                            try:
                                cb(symbol, price)
                            except Exception as e:
                                print(f"[IBKRClient] Callback error: {e}")

        def historicalData(reqId: int, bar: BarData):
            client._hist_bars.append(bar)

        def historicalDataEnd(reqId: int, start: str, end: str):
            client._hist_event.set()

        def orderStatus(orderId: int, status: str, filled: float,
                        remaining: float, avgFillPrice: float, permId: int,
                        parentId: int, lastFillPrice: float, clientId: int,
                        whyHeld: str, mktCapPrice: float):
            if status in ("Filled", "PreSubmitted", "Submitted"):
                if avgFillPrice > 0:
                    client._order_fills[orderId] = avgFillPrice
                    ev = client._order_events.get(orderId)
                    if ev:
                        ev.set()

        def accountSummary(reqId: int, account: str,
                           tag: str, value: str, currency: str):
            if tag == "NetLiquidation":
                try:
                    client._nlv = float(value)
                    client._nlv_event.set()
                except ValueError:
                    pass

        def contractDetails(reqId: int, contractDetails):
            client._contract_details.append(contractDetails)

        def contractDetailsEnd(reqId: int):
            client._contract_event.set()

        def error(reqId: int, errorCode: int, errorString: str,
                  advancedOrderRejectJson: str = ""):
            ignorable = {2104, 2106, 2108, 2158, 2119}
            if errorCode not in ignorable:
                print(f"[IBKR] Error {errorCode} (req={reqId}): {errorString}")
            if reqId in client._order_events:
                client._order_events[reqId].set()

        self._app.nextValidId         = nextValidId
        self._app.tickPrice           = tickPrice
        self._app.historicalData      = historicalData
        self._app.historicalDataEnd   = historicalDataEnd
        self._app.orderStatus         = orderStatus
        self._app.accountSummary      = accountSummary
        self._app.contractDetails     = contractDetails
        self._app.contractDetailsEnd  = contractDetailsEnd
        self._app.error               = error

    # ── ID generator ─────────────────────────────────────────────────────────
    def _new_id(self) -> int:
        with self._lock:
            req_id     = self._next_id
            self._next_id += 1
            return req_id

    # ── Live subscriptions ────────────────────────────────────────────────────
    def subscribe_live(self, symbol: str, callback: Callable):
        """
        Subscribe to real-time last price for symbol.
        VIX / VIX9D use secType="IND" and exchange="CBOE".
        Underlying equities use secType="STK" and exchange="SMART".
        """
        contract = self._make_contract(symbol)
        req_id   = self._new_id()
        with self._lock:
            self._req_symbol[req_id] = symbol
            if symbol not in self._callbacks:
                self._callbacks[symbol] = []
            self._callbacks[symbol].append(callback)
        self._app.reqMktData(req_id, contract, "", False, False, [])
        return req_id

    # ── Current price reads ───────────────────────────────────────────────────
    def _get_tick(self, symbol: str, key: str) -> Optional[float]:
        """Look up the latest tick value for a symbol's tick type."""
        with self._lock:
            for req_id, sym in self._req_symbol.items():
                if sym == symbol:
                    return self._live_ticks.get(req_id, {}).get(key)
        return None

    def get_vix_live(self) -> Optional[float]:
        return self._get_tick("VIX", "last")

    def get_vix9d_live(self) -> Optional[float]:
        return self._get_tick("VIX9D", "last")

    def get_bid(self, contract: Contract) -> float:
        v = self._get_tick(contract.symbol, "bid")
        return v if v else 0.0

    def get_ask(self, contract: Contract) -> float:
        v = self._get_tick(contract.symbol, "ask")
        return v if v else 0.0

    def get_option_price(self, contract: Contract) -> float:
        bid = self.get_bid(contract)
        ask = self.get_ask(contract)
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2, 2)
        last = self._get_tick(contract.symbol, "last")
        return last if last else 0.0

    # ── Historical daily closes ───────────────────────────────────────────────
    def get_historical_daily_closes(self, symbol: str,
                                    n_days: int = 20) -> list:
        """
        Returns list[DailyClose] sorted oldest → newest.
        useRTH=False captures the 4:15 PM settlement print as the close.
        """
        contract   = self._make_contract(symbol)
        duration   = f"{n_days + 5} D"
        end_dt     = ""    # empty = now
        bar_size   = "1 day"
        what_to_show = "TRADES"
        use_rth    = 0     # 0 = include extended hours (captures 4:15 close)

        self._hist_bars  = []
        self._hist_event.clear()
        req_id = self._new_id()
        self._app.reqHistoricalData(
            req_id, contract, end_dt, duration,
            bar_size, what_to_show, use_rth, 1, False, []
        )
        self._hist_event.wait(timeout=30)

        closes = []
        for bar in self._hist_bars:
            try:
                d = date.fromisoformat(bar.date[:10])
                closes.append(DailyClose(trade_date=d, close=bar.close))
            except Exception:
                continue
        closes.sort(key=lambda x: x.trade_date)
        return closes[-n_days:]

    # ── Option contract resolution ────────────────────────────────────────────
    def get_option_contract(self, symbol: str, right: str,
                            strike_method: str, strike_val: float,
                            dte: int) -> Contract:
        """
        Resolve a concrete option contract from the chain.
        strike_method : "delta" | "fixed_premium" | "strike_offset" | "pct_otm"
        """
        expiry = self._expiry_from_dte(dte)
        chain  = self._get_chain(symbol, right, expiry)
        if not chain:
            raise RuntimeError(f"No option chain found for {symbol} "
                               f"{right} expiry={expiry}")

        underlying = self._get_tick(symbol, "last") or 0.0

        if strike_method == "delta":
            return self._best_by_delta(chain, strike_val, underlying, right)
        if strike_method == "fixed_premium":
            return self._best_by_premium(chain, strike_val)
        if strike_method == "strike_offset":
            return self._best_by_offset(chain, int(strike_val), underlying)
        if strike_method == "pct_otm":
            target = underlying * (1 + strike_val / 100) \
                     if right == "C" \
                     else underlying * (1 - strike_val / 100)
            return self._nearest_strike(chain, target)
        raise ValueError(f"Unknown strike_method: {strike_method}")

    # ── Orders ────────────────────────────────────────────────────────────────
    def place_limit_order(self, contract: Contract,
                          action: str, quantity: int,
                          price: float, timeout: int = 30) -> Optional[float]:
        order           = Order()
        order.action    = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice  = round(price, 2)
        order.tif       = "DAY"

        order_id = self._new_id()
        ev       = threading.Event()
        self._order_events[order_id] = ev
        self._app.placeOrder(order_id, contract, order)
        ev.wait(timeout=timeout)

        fill = self._order_fills.pop(order_id, None)
        self._order_events.pop(order_id, None)
        if fill:
            self._app.cancelOrder(order_id, "")
        return fill

    def place_market_order(self, contract: Contract,
                           action: str, quantity: int) -> float:
        order               = Order()
        order.action        = action
        order.orderType     = "MKT"
        order.totalQuantity = quantity
        order.tif           = "DAY"

        order_id = self._new_id()
        ev       = threading.Event()
        self._order_events[order_id] = ev
        self._app.placeOrder(order_id, contract, order)
        ev.wait(timeout=60)

        fill = self._order_fills.pop(order_id, None)
        self._order_events.pop(order_id, None)
        return fill or 0.0

    # ── Account ───────────────────────────────────────────────────────────────
    def get_account_nlv(self) -> float:
        self._nlv       = None
        self._nlv_event.clear()
        req_id = self._new_id()
        self._app.reqAccountSummary(req_id, "All", "NetLiquidation")
        self._nlv_event.wait(timeout=10)
        self._app.cancelAccountSummary(req_id)
        return self._nlv or 0.0

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _make_contract(self, symbol: str) -> Contract:
        c          = Contract()
        c.currency = "USD"
        if symbol in ("VIX", "VIX9D", "VXN"):
            c.symbol   = symbol
            c.secType  = "IND"
            c.exchange = "CBOE"
        else:
            c.symbol   = symbol
            c.secType  = "STK"
            c.exchange = "SMART"
        return c

    @staticmethod
    def _expiry_from_dte(dte: int) -> str:
        target = datetime.today() + timedelta(days=dte)
        return target.strftime("%Y%m%d")

    def _get_chain(self, symbol: str, right: str, expiry: str) -> list:
        c          = Contract()
        c.symbol   = symbol
        c.secType  = "OPT"
        c.exchange = "SMART"
        c.currency = "USD"
        c.right    = right
        c.lastTradeDateOrContractMonth = expiry

        self._contract_details = []
        self._contract_event.clear()
        req_id = self._new_id()
        self._app.reqContractDetails(req_id, c)
        self._contract_event.wait(timeout=20)
        return [cd.contract for cd in self._contract_details]

    def _best_by_delta(self, chain: list, target_delta: float,
                       underlying: float, right: str) -> Contract:
        """Approximate delta by strike distance from ATM (no Greeks needed)."""
        best, best_diff = chain[0], float("inf")
        for c in chain:
            diff = abs(c.strike - underlying)
            if abs(diff - target_delta * underlying) < best_diff:
                best_diff = abs(diff - target_delta * underlying)
                best      = c
        return best

    def _best_by_premium(self, chain: list, target_premium: float) -> Contract:
        best, best_diff = chain[0], float("inf")
        for c in chain:
            price = self.get_option_price(c)
            if abs(price - target_premium) < best_diff:
                best_diff = abs(price - target_premium)
                best      = c
        return best

    def _best_by_offset(self, chain: list,
                        offset: int, underlying: float) -> Contract:
        sorted_chain = sorted(chain, key=lambda c: c.strike)
        atm_idx = min(range(len(sorted_chain)),
                      key=lambda i: abs(sorted_chain[i].strike - underlying))
        target_idx = max(0, min(len(sorted_chain) - 1, atm_idx + offset))
        return sorted_chain[target_idx]

    def _nearest_strike(self, chain: list, target: float) -> Contract:
        return min(chain, key=lambda c: abs(c.strike - target))