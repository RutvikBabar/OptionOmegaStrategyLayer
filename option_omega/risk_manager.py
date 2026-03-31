"""
risk_manager.py
===============
Stateful per-trade risk management. Thread-safe. No I/O — pure logic on state.
"""

import threading


class RiskManager:

    def __init__(self, config):
        self.cfg              = config
        self.entry_price      = None
        self.highest_price    = None
        self.daily_loss       = 0.0
        self.trades_today     = 0
        self.open_positions   = 0
        self._lock            = threading.Lock()
        self._consecutive_hits = 0

    # ── Entry ─────────────────────────────────────────────────────────────────
    def set_entry(self, price: float):
        with self._lock:
            self.entry_price   = price
            self.highest_price = price

    def record_entry(self):
        with self._lock:
            self.open_positions += 1

    # ── Price update ──────────────────────────────────────────────────────────
    def update_price(self, price: float):
        with self._lock:
            if self.highest_price is None or price > self.highest_price:
                self.highest_price = price

    # ── Exit recording ────────────────────────────────────────────────────────
    def record_exit(self, exit_price: float):
        with self._lock:
            if self.entry_price:
                pnl = (exit_price - self.entry_price) * 100
                self.daily_loss += min(0, pnl)
            self.trades_today     += 1
            self.open_positions    = max(0, self.open_positions - 1)
            self.entry_price       = None
            self.highest_price     = None
            self._consecutive_hits = 0

    # ── Daily guards ──────────────────────────────────────────────────────────
    def is_daily_loss_breached(self) -> bool:
        return abs(self.daily_loss) >= self.cfg.max_daily_loss

    def is_max_trades_reached(self) -> bool:
        return self.trades_today >= self.cfg.max_trades_per_day

    def is_max_open_positions_reached(self) -> bool:
        return self.open_positions >= self.cfg.max_open_positions

    # ── P&L helpers ───────────────────────────────────────────────────────────
    def pnl_pct(self, current_price: float) -> float:
        if not self.entry_price:
            return 0.0
        return (current_price - self.entry_price) / self.entry_price

    # ── Exit checks ───────────────────────────────────────────────────────────
    def check_stop_loss(self, current_price: float) -> bool:
        if not self.entry_price:
            return False
        loss_pct = (self.entry_price - current_price) / self.entry_price
        return loss_pct >= self.cfg.stop_loss_pct

    def check_trailing_stop(self, current_price: float) -> bool:
        sl = self.cfg.stop_loss
        if not sl.trailing_enabled or self.highest_price is None:
            return False
        gain = (self.highest_price - self.entry_price) / self.entry_price \
               if self.entry_price else 0.0
        if gain < sl.trailing_trigger_pct:
            return False
        drop = (self.highest_price - current_price) / self.highest_price
        return drop >= sl.trailing_stop_pct

    def check_profit_target(self, current_price: float) -> bool:
        if not self.entry_price:
            return False
        gain_pct = (current_price - self.entry_price) / self.entry_price
        return gain_pct >= self.cfg.profit_target_pct

    def check_breakeven(self, current_price: float) -> bool:
        """Returns True once gain exceeds breakeven_trigger — caller moves SL to entry."""
        if not self.entry_price:
            return False
        gain_pct = (current_price - self.entry_price) / self.entry_price
        return gain_pct >= self.cfg.breakeven_trigger

    def check_intra_minute_stop(self, current_price: float) -> bool:
        if not self.entry_price:
            return False
        if (self.entry_price - current_price) / self.entry_price \
                >= self.cfg.stop_loss_pct:
            self._consecutive_hits += 1
        else:
            self._consecutive_hits = 0
        return self._consecutive_hits >= \
               self.cfg.stop_loss.intra_min_consecutive_hits