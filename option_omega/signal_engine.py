"""
signal_engine.py
================
Generates entry/exit signals. Replace or extend _generate_signal()
with your own logic (momentum, mean-reversion, ML model output, etc.).

The default stub fires a long signal when the underlying has moved
more than `trigger_pct` from the day open (same behaviour as the
original Option Omega move filter).

set_open() must be called once per day when the RTH open is known
(DataPuller does this automatically via DataStore.set_rth_open).
"""

from typing import Optional


class SignalEngine:

    def __init__(self, config):
        self.cfg      = config
        self.day_open: Optional[float] = None

    def set_open(self, price: float):
        self.day_open = price

    def move_pct(self, current_price: float) -> float:
        if not self.day_open:
            return 0.0
        return (current_price - self.day_open) / self.day_open

    def move_pts(self, current_price: float) -> float:
        if not self.day_open:
            return 0.0
        return current_price - self.day_open

    def generate(self, current_price: float) -> Optional[dict]:
        """
        Returns a signal dict on a valid entry, None otherwise.

        Signal dict keys
        ----------------
          right       : "C" | "P"
          strike_val  : value passed to ibkr.get_option_contract()
                        (delta, premium, offset, or % OTM — matches
                         cfg.strike_method)
          direction   : "long" | "short"
        """
        if not self.day_open:
            return None

        move = self.move_pct(current_price)

        if abs(move) < self.cfg.trigger_pct:
            return None

        right = "C" if move > 0 else "P"
        return {
            "right":      right,
            "strike_val": self.cfg.min_delta,
            "direction":  "long",
        }