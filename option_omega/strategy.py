"""
strategy.py
===========
Main strategy loop for Option Omega.

State machine
-------------
  IDLE      → on start() → SCANNING
  SCANNING  → filters pass + signal fires → ENTERING
  ENTERING  → order filled → IN_TRADE
  IN_TRADE  → exit condition met → EXITING
  EXITING   → exit filled → SCANNING  (or EXITED if daily limits hit)
  EXITED    → terminal (daily loss / max trades)

Data flow
---------
  DataPuller (daemon) owns all IBKR subscriptions and writes MinuteBars +
  VixSnaps + IndicatorCache into DataStore every minute.
  Strategy reads ONLY from DataStore — zero IBKR calls in the hot loop.
  IBKR calls only happen in _enter_trade() and _exit_trade() via OrderManager.
"""

import threading
import time
from datetime import datetime, time as dtime
from typing   import Optional

from config             import StrategyConfig
from signal_engine      import SignalEngine
from risk_manager       import RiskManager
from market_filter      import MarketFilter
from allocation_manager import AllocationManager
from order_manager      import OrderManager
from data_store         import get_store


class OptionOmegaStrategy:

    def __init__(self, config: StrategyConfig, ibkr,
                 signal: SignalEngine, risk: RiskManager):
        self.cfg    = config
        self.ibkr   = ibkr
        self.signal = signal
        self.risk   = risk
        self.mf     = MarketFilter(config)
        self.alloc  = AllocationManager(ibkr, config)
        self.om     = OrderManager(ibkr)
        self._store = get_store()

        self.state:           str             = "IDLE"
        self.position                         = None
        self.entry_fill_price: Optional[float] = None
        self.log:             list             = []
        self.trade_history:   list             = []
        self._stop_event      = threading.Event()
        self._breakeven_set:  bool             = False

    # ── Logging ───────────────────────────────────────────────────────────────
    def _log(self, msg: str):
        ts    = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.log.append(entry)
        print(entry)

    # ── Public API ────────────────────────────────────────────────────────────
    def run(self):
        self._stop_event.clear()
        t = threading.Thread(
            target=self._main_loop,
            name=f"oo_strategy_{self.cfg.client_id}",
            daemon=True,
        )
        t.start()

    def stop(self):
        self._stop_event.set()
        self._log("Strategy stop requested")

    # ── Main loop ─────────────────────────────────────────────────────────────
    def _main_loop(self):
        self._log(f"Strategy '{self.cfg.name}' started — "
                  f"symbol={self.cfg.symbol}")
        self.state = "SCANNING"

        while not self._stop_event.is_set():
            try:
                now = datetime.now().time()

                # ── Daily guards ─────────────────────────────────────────────
                if self.risk.is_daily_loss_breached():
                    self._log("Daily loss limit reached — shutting down")
                    self.state = "EXITED"
                    return
                if self.risk.is_max_trades_reached():
                    self._log("Max daily trades reached — shutting down")
                    self.state = "EXITED"
                    return

                # ── In-trade exit monitoring ──────────────────────────────────
                if self.state == "IN_TRADE":
                    self._monitor_exit()
                    time.sleep(1)
                    continue

                # ── Entry window guard ────────────────────────────────────────
                if not self._in_entry_window(now):
                    time.sleep(10)
                    continue

                # ── Lock RTH open from DataStore (set by DataPuller) ─────────
                if self.signal.day_open is None:
                    open_price = self._store.get_rth_open(self.cfg.symbol)
                    if open_price:
                        self.signal.set_open(open_price)
                        self._log(f"Day open locked: {open_price:.2f}")

                # ── SCANNING: look for entry ───────────────────────────────────
                if self.state == "SCANNING":
                    if self.risk.is_max_open_positions_reached():
                        self._log("Max open positions reached — waiting")
                        time.sleep(30)
                        continue
                    self._check_entry()

                time.sleep(2)

            except Exception as e:
                self._log(f"[ERROR] Main loop exception: {e}")
                time.sleep(5)

    # ── Entry check ───────────────────────────────────────────────────────────
    def _check_entry(self):
        price = self._store.get_latest_close(self.cfg.symbol)
        if price is None:
            return

        # Market filters
        passed, reason = self.mf.check_all()
        if not passed:
            self._log(f"Filters blocked entry: {reason}")
            return

        # Signal
        sig = self.signal.generate(price)
        if not sig:
            return

        self._log(f"Signal fired — entering trade: {sig}")
        self.state = "ENTERING"
        fill = self._enter_trade(sig, price)
        if fill:
            self.state = "IN_TRADE"
            self._breakeven_set = False
        else:
            self._log("Entry abandoned — returning to SCANNING")
            self.state = "SCANNING"

    # ── Enter trade ───────────────────────────────────────────────────────────
    def _enter_trade(self, signal, price: float) -> float:
        try:
            contract = self.ibkr.get_option_contract(
                symbol       = self.cfg.symbol,
                right        = signal.get("right", "C"),
                strike_method = self.cfg.strike_method,
                strike_val   = signal.get("strike_val", self.cfg.min_delta),
                dte          = self.cfg.dte,
            )
        except Exception as e:
            self._log(f"[ERROR] Contract lookup failed: {e}")
            return 0.0

        try:
            mid = self.ibkr.get_option_price(contract)
        except Exception as e:
            self._log(f"[ERROR] Option price fetch failed: {e}")
            return 0.0

        qty  = self.alloc.get_quantity(mid)
        fill = self.om.enter(contract, qty, self.cfg.entry_execution)

        if fill:
            self.position          = contract
            self.entry_fill_price  = fill
            self.risk.set_entry(fill)
            self.risk.record_entry()
            self._log(f"Entered {qty}x {contract.symbol} @ {fill:.2f}")
        return fill

    # ── Exit monitoring ───────────────────────────────────────────────────────
    def _monitor_exit(self):
        if self.position is None:
            return

        try:
            current = self.ibkr.get_option_price(self.position)
        except Exception:
            return

        self.risk.update_price(current)
        pnl = self.risk.pnl_pct(current)

        # Breakeven trigger (move stop loss to entry — one-time per trade)
        if not self._breakeven_set and self.risk.check_breakeven(current):
            self.cfg.stop_loss.loss_pct = 0.0
            self._breakeven_set = True
            self._log(f"Breakeven set — stop moved to entry "
                      f"(current pnl={pnl:+.2%})")

        # Profit target
        if self.risk.check_profit_target(current):
            self._log(f"Profit target hit @ {current:.2f} "
                      f"(pnl={pnl:+.2%})")
            self._exit_trade("PROFIT_TARGET")
            return

        # Trailing stop
        if self.risk.check_trailing_stop(current):
            self._log(f"Trailing stop triggered @ {current:.2f} "
                      f"(pnl={pnl:+.2%})")
            self._exit_trade("TRAILING_STOP")
            return

        # Hard stop loss
        if self.risk.check_stop_loss(current):
            self._log(f"Stop loss triggered @ {current:.2f} "
                      f"(pnl={pnl:+.2%})")
            self._exit_trade("STOP_LOSS")
            return

        # VIX9D exit condition
        vix_exit, vix_reason = self.mf.check_vix_exit()
        if not vix_exit:
            self._log(f"VIX exit condition triggered: {vix_reason}")
            self._exit_trade("VIX_EXIT")
            return

        # Intra-minute stop (consecutive hit check)
        if self.risk.check_intra_minute_stop(current):
            self._log(f"Intra-minute stop triggered @ {current:.2f}")
            self._exit_trade("INTRA_MIN_STOP")
            return

        # Timed / end-of-day exit
        now = datetime.now().time()
        if self.cfg.window_end and now >= self.cfg.window_end:
            self._log(f"Exit window reached ({self.cfg.window_end}) — "
                      f"closing position")
            self._exit_trade("TIMED_EXIT")

    # ── Exit trade ────────────────────────────────────────────────────────────
    def _exit_trade(self, reason: str):
        if self.position is None:
            return

        self.state = "EXITING"
        self._log(f"Exiting trade — reason: {reason}")

        try:
            qty  = 1   # adjust for multi-leg when legs implemented
            fill = self.om.exit(
                contract       = self.position,
                quantity       = qty,
                cfg            = self.cfg.exit_execution,
                bid_ask_filter = self.cfg.bid_ask_filter,
            )
        except Exception as e:
            self._log(f"[ERROR] Exit order failed: {e}")
            fill = 0.0

        exit_price = fill or self.entry_fill_price or 0.0
        self.risk.record_exit(exit_price)

        self.trade_history.append({
            "entry":  self.entry_fill_price,
            "exit":   exit_price,
            "reason": reason,
            "pnl":    self.risk.pnl_pct(exit_price),
            "time":   datetime.now().strftime("%H:%M:%S"),
        })

        self._log(f"Exit complete — fill={exit_price:.2f}  "
                  f"pnl={self.risk.pnl_pct(exit_price):+.2%}")

        self.position         = None
        self.entry_fill_price = None
        self.state            = "SCANNING"

    # ── Entry window ──────────────────────────────────────────────────────────
    def _in_entry_window(self, now: dtime) -> bool:
        mode = self.cfg.entry_time_mode
        if mode == "Window":
            start = self.cfg.window_start
            end   = self.cfg.window_end
            if start and end:
                return start <= now <= end
            return True
        if mode == "Fixed Entry Times":
            cur_hm = now.strftime("%H:%M")
            return cur_hm in self.cfg.fixed_entry_times
        return True