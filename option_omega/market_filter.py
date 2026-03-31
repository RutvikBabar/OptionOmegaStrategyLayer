"""
market_filter.py
================
All entry/exit filter checks. Reads ONLY from DataStore — zero IBKR calls.

Filters implemented
-------------------
  VIX Range            — min/max VIX (per minute, from DataStore)
  VIX Overnight        — prev close → current VIX (% or pts)
  VIX Intraday         — RTH open → current VIX (% or pts)
  VIX9D/VIX Ratio      — entry + optional separate exit
  Gap (underlying)     — prev close → RTH open (% or pts)
  Intraday Move        — RTH open → current price (% or pts)
  RSI / SMA / EMA      — from IndicatorCache in DataStore
"""

from data_store import get_store, UNIT_PCT, UNIT_POINTS
from config     import StrategyConfig
from typing     import Optional


class MarketFilter:

    def __init__(self, config: StrategyConfig):
        self.cfg    = config
        self._store = get_store()

    # ── Master entry check ────────────────────────────────────────────────────
    def check_all(self) -> tuple[bool, str]:
        checks = [
            self._check_vix_range,
            self._check_vix_overnight,
            self._check_vix_intraday,
            self._check_vix9d_entry,
            self._check_gap,
            self._check_intraday_move,
            self._check_rsi,
            self._check_sma,
            self._check_ema,
        ]
        for fn in checks:
            passed, reason = fn()
            if not passed:
                return False, reason
        return True, "All filters passed"

    # ── VIX exit check (non-blocking if VIX9D not printed) ────────────────────
    def check_vix_exit(self) -> tuple[bool, str]:
        """
        Returns (True, reason) to ALLOW exit, (False, reason) to BLOCK exit.
        If VIX9D has not printed → returns (True, "VIX9D not printed — skip")
        so other exit conditions are unaffected.
        """
        f = self.cfg.vix.vix9d
        if not f.enabled or not f.use_exit:
            return True, "VIX9D exit not enabled"

        snap = self._store.get_latest_vix()
        if snap is None or snap.vix9d <= 0:
            return True, "VIX9D not printed — skip exit condition"

        if snap.vix <= 0:
            return True, "VIX not available"

        ratio = snap.vix9d / snap.vix
        if f.exit_min_ratio <= ratio <= f.exit_max_ratio:
            return False, f"VIX9D/VIX exit condition triggered: ratio={ratio:.4f}"
        return True, f"VIX9D/VIX ratio {ratio:.4f} not in exit range"

    # ── VIX Range ─────────────────────────────────────────────────────────────
    def _check_vix_range(self) -> tuple[bool, str]:
        f = self.cfg.vix.range
        if not f.enabled:
            return True, "VIX range not enabled"
        snap = self._store.get_latest_vix()
        if snap is None:
            return False, "VIX data not available"
        vix = snap.vix
        if f.min_vix <= vix <= f.max_vix:
            return True, f"VIX {vix:.2f} in range [{f.min_vix}, {f.max_vix}]"
        return False, f"[VIX BLOCK] VIX {vix:.2f} outside range"

    # ── VIX Overnight ─────────────────────────────────────────────────────────
    def _check_vix_overnight(self) -> tuple[bool, str]:
        f = self.cfg.vix.overnight
        if not f.enabled:
            return True, "VIX overnight not enabled"

        snap = self._store.get_latest_vix()
        snaps = self._store.get_vix_snaps()
        if not snap or len(snaps) < 2:
            return False, "Not enough VIX data for overnight check"

        # prev close = last snap before 09:25
        prev_snaps = [s for s in snaps if s.ts < "09:25"]
        if not prev_snaps:
            return False, "No pre-market VIX data"
        prev_close = prev_snaps[-1].vix
        current    = snap.vix

        move = self._calc_move(prev_close, current, f.unit)
        direction_ok = self._direction_ok(prev_close, current, f.direction)

        if direction_ok and abs(move) >= f.threshold:
            return True, f"VIX overnight move {move:+.3f} passes"
        return False, (f"[VIX BLOCK] VIX overnight move {move:+.3f} "
                       f"below threshold {f.threshold} / direction={f.direction}")

    # ── VIX Intraday ──────────────────────────────────────────────────────────
    def _check_vix_intraday(self) -> tuple[bool, str]:
        """
        Intraday VIX: RTH open (09:25 print) → current candle open at 1-min bar.
        Per OO spec: uses candle open value of the current 1-min bar.
        """
        f = self.cfg.vix.intraday
        if not f.enabled:
            return True, "VIX intraday not enabled"

        vix_open = self._store.get_vix_rth_open()
        snap     = self._store.get_latest_vix()
        if vix_open is None or snap is None:
            return False, "VIX RTH open or current VIX not available"

        current  = snap.vix
        move     = self._calc_move(vix_open, current, f.unit)
        abs_move = abs(move)
        direction_ok = self._direction_ok(vix_open, current, f.direction)

        if direction_ok and f.min_move <= abs_move <= f.max_move:
            return True, f"VIX intraday move {move:+.3f} passes"
        return False, (f"[VIX ID] VIX intraday move {move:+.3f} "
                       f"out of range [{f.min_move}, {f.max_move}]")

    # ── VIX9D/VIX Entry ───────────────────────────────────────────────────────
    def _check_vix9d_entry(self) -> tuple[bool, str]:
        """
        VIX9D/VIX ratio entry.
        If VIX9D has not printed → block entry (per OO spec).
        Uses minute-bar open values (latest snap as proxy).
        """
        f = self.cfg.vix.vix9d
        if not f.enabled:
            return True, "VIX9D ratio not enabled"

        snap = self._store.get_latest_vix()
        if snap is None or snap.vix9d <= 0:
            return False, "[VIX BLOCK] VIX9D not printed — entry blocked"
        if snap.vix <= 0:
            return False, "[VIX BLOCK] VIX not available"

        ratio = snap.vix9d / snap.vix
        if f.entry_min_ratio <= ratio <= f.entry_max_ratio:
            return True, f"VIX9D/VIX ratio {ratio:.4f} in entry range"
        return False, (f"[VIX BLOCK] VIX9D/VIX ratio {ratio:.4f} "
                       f"outside entry range [{f.entry_min_ratio}, {f.entry_max_ratio}]")

    # ── Underlying Gap ────────────────────────────────────────────────────────
    def _check_gap(self) -> tuple[bool, str]:
        """
        Overnight gap: previous trading day close → official RTH open.
        Positive numbers; direction = "up" | "down" | "both".
        """
        f = self.cfg.gap
        if not f.enabled:
            return True, "Gap filter not enabled"

        symbol    = self.cfg.symbol
        rth_open  = self._store.get_rth_open(symbol)
        daily     = self._store.get_daily_closes(symbol)

        if rth_open is None:
            return False, "RTH open not locked yet"
        if not daily:
            return False, "No daily closes available"

        prev_close   = daily[-1].close
        move         = self._calc_move(prev_close, rth_open, f.unit)
        abs_move     = abs(move)
        direction_ok = self._direction_ok(prev_close, rth_open, f.direction)

        if direction_ok and f.min_gap <= abs_move <= f.max_gap:
            return True, f"Gap {move:+.3f} passes"
        return False, (f"Gap {move:+.3f} outside range "
                       f"[{f.min_gap}, {f.max_gap}] / direction={f.direction}")

    # ── Underlying Intraday Move ───────────────────────────────────────────────
    def _check_intraday_move(self) -> tuple[bool, str]:
        """
        Intraday move: daily open (1-min candle open) → current price.
        Per OO spec: uses candle open of the 1-min bar at entry time.
        """
        f = self.cfg.intraday
        if not f.enabled:
            return True, "Intraday move filter not enabled"

        symbol      = self.cfg.symbol
        rth_open    = self._store.get_rth_open(symbol)
        current     = self._store.get_latest_close(symbol)

        if rth_open is None or current is None:
            return False, "RTH open or current price not available"

        move         = self._calc_move(rth_open, current, f.unit)
        abs_move     = abs(move)
        direction_ok = self._direction_ok(rth_open, current, f.direction)

        if direction_ok and f.min_move <= abs_move <= f.max_move:
            return True, f"Intraday move {move:+.3f} passes"
        return False, (f"Intraday move {move:+.3f} outside range "
                       f"[{f.min_move}, {f.max_move}] / direction={f.direction}")

    # ── RSI ───────────────────────────────────────────────────────────────────
    def _check_rsi(self) -> tuple[bool, str]:
        f = self.cfg.technicals.rsi
        if not f.enabled:
            return True, "RSI not enabled"

        ind = self._store.get_indicators(self.cfg.symbol)
        if ind is None or ind.rsi14 is None:
            return False, "RSI not computed yet"

        rsi = ind.rsi14
        if f.min_rsi <= rsi <= f.max_rsi:
            return True, f"RSI {rsi:.2f} in range [{f.min_rsi}, {f.max_rsi}]"
        return False, f"RSI {rsi:.2f} outside range [{f.min_rsi}, {f.max_rsi}]"

    # ── SMA ───────────────────────────────────────────────────────────────────
    def _check_sma(self) -> tuple[bool, str]:
        f = self.cfg.technicals.sma
        if not f.enabled:
            return True, "SMA not enabled"

        ind = self._store.get_indicators(self.cfg.symbol)
        if ind is None:
            return False, "Indicators not computed yet"

        sma = ind.sma.get(f.period)
        if sma is None:
            return False, f"SMA-{f.period} not computed yet"

        current = self._store.get_latest_close(self.cfg.symbol)
        if current is None:
            return False, "Current price not available"

        if f.condition == "above" and current >= sma:
            return True, f"Price {current:.2f} above SMA-{f.period} {sma:.2f}"
        if f.condition == "below" and current <= sma:
            return True, f"Price {current:.2f} below SMA-{f.period} {sma:.2f}"
        return False, (f"Price {current:.2f} not {f.condition} "
                       f"SMA-{f.period} {sma:.2f}")

    # ── EMA ───────────────────────────────────────────────────────────────────
    def _check_ema(self) -> tuple[bool, str]:
        f = self.cfg.technicals.ema
        if not f.enabled:
            return True, "EMA not enabled"

        ind = self._store.get_indicators(self.cfg.symbol)
        if ind is None:
            return False, "Indicators not computed yet"

        ema = ind.ema.get(f.period)
        if ema is None:
            return False, f"EMA-{f.period} not computed yet"

        current = self._store.get_latest_close(self.cfg.symbol)
        if current is None:
            return False, "Current price not available"

        if f.condition == "above" and current >= ema:
            return True, f"Price {current:.2f} above EMA-{f.period} {ema:.2f}"
        if f.condition == "below" and current <= ema:
            return True, f"Price {current:.2f} below EMA-{f.period} {ema:.2f}"
        return False, (f"Price {current:.2f} not {f.condition} "
                       f"EMA-{f.period} {ema:.2f}")

    # ── Calculation helpers ────────────────────────────────────────────────────
    @staticmethod
    def _calc_move(base: float, current: float, unit: str) -> float:
        """Returns signed move in either % or absolute points."""
        if base == 0:
            return 0.0
        if unit == UNIT_PCT:
            return (current - base) / base * 100.0
        return current - base   # UNIT_POINTS

    @staticmethod
    def _direction_ok(base: float, current: float, direction: str) -> bool:
        if direction == "up":
            return current >= base
        if direction == "down":
            return current <= base
        return True   # "both"