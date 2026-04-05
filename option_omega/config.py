from dataclasses import dataclass, field
from datetime import time
from typing import List, Optional, Dict

# ── Strike Selection ──────────────────────────────────────────────────────────

@dataclass
class LegConfig:
    leg_id: int = 1
    parent_id: int = 0           # 0 = standalone parent
    action: str = "SELL"         # BUY | SELL
    right: str = "PUT"           # PUT | CALL
    quantity: int = 1
    strike_method: str = "delta" # delta | pct_otm | fixed_premium | strike_offset
    strike_val: float = 0.30
    dte: int = 0
    exact_dte: bool = False
    child_offset: float = 0.0
    child_method: str = "offset"     # offset | delta | fixed_premium
    child_strike_val: float = 0.0
    child_max_width: float = 0.0
    exact_strike_lock: bool = True
    leg_group: int = 0               # SEME group
    round_strikes_multiple: int = 0


# ── Execution ─────────────────────────────────────────────────────────────────

@dataclass
class EntryExecution:
    starting_offset: float = 0.0
    price_adjustment: float = 0.10
    interval_seconds: int = 30
    max_attempts: int = 5
    retry_minutes: int = 0
    use_market_after_attempts: bool = True

@dataclass
class ExitExecution:
    starting_offset: float = 0.0
    price_adjustment: float = 0.10
    interval_seconds: int = 30
    max_attempts: int = 5
    use_market_after_attempts: bool = True
    ignore_bidless_longs: bool = False

@dataclass
class BidAskFilter:
    enabled: bool = False
    mode: str = "percentage"   # percentage | fixed
    max_spread_width: float = 0.40
    max_attempts: int = 10


# ── Funds & Allocation ────────────────────────────────────────────────────────

@dataclass
class FundsConfig:
    starting_funds: float = 10000.0
    margin_allocation_pct: float = 10.0
    max_open_trades: int = 1
    prune_oldest_trades: bool = False
    max_contracts_per_trade: int = 0           # 0 = dynamic
    ignore_margin_requirements: bool = False
    max_allocation_per_trade: float = 0.0


# ── VIX Filters ───────────────────────────────────────────────────────────────

@dataclass
class VixRangeFilter:
    enabled: bool = False
    min_vix: float = 0.0
    max_vix: float = 999.0

@dataclass
class VixOvernightFilter:
    enabled: bool = False
    direction: str = "both"   # up | down | both
    unit: str = "pct"         # pct | pts
    threshold: float = 0.0

@dataclass
class VixIntradayFilter:
    enabled: bool = False
    direction: str = "both"
    unit: str = "pct"
    min_move: float = 0.0
    max_move: float = 999.0

@dataclass
class Vix9dRatioFilter:
    enabled: bool = False
    entry_min_ratio: float = 0.0
    entry_max_ratio: float = 999.0
    use_exit: bool = False
    exit_min_ratio: float = 0.0
    exit_max_ratio: float = 999.0

@dataclass
class VixFilters:
    range: VixRangeFilter = field(default_factory=VixRangeFilter)
    overnight: VixOvernightFilter = field(default_factory=VixOvernightFilter)
    intraday: VixIntradayFilter = field(default_factory=VixIntradayFilter)
    vix9d: Vix9dRatioFilter = field(default_factory=Vix9dRatioFilter)


# ── Gap / Intraday Move ───────────────────────────────────────────────────────

@dataclass
class GapFilter:
    enabled: bool = False
    direction: str = "both"
    unit: str = "pct"
    min_gap: float = 0.0
    max_gap: float = 999.0

@dataclass
class IntradayMoveFilter:
    enabled: bool = False
    direction: str = "both"
    unit: str = "pct"
    min_move: float = 0.0
    max_move: float = 999.0


# ── SqueezeMetrics ────────────────────────────────────────────────────────────

@dataclass
class SqueezeMetricsFilter:
    enabled: bool = False
    min_dix: float = 0.0
    max_dix: float = 100.0
    min_gex: float = -999.0
    max_gex: float = 999.0


# ── Opening Range Breakout ────────────────────────────────────────────────────

@dataclass
class OrbFilter:
    enabled: bool = False
    end_time: str = "09:45"
    condition: str = "high_and_low"  # high_and_low | high_only | low_only | no_breakout
    use_high_low_wicks: bool = False


# ── Technical Indicators ──────────────────────────────────────────────────────

@dataclass
class RsiFilter:
    enabled: bool = False
    period: int = 14
    min_rsi: float = 0.0
    max_rsi: float = 100.0

@dataclass
class SmaFilter:
    enabled: bool = False
    period: int = 20
    condition: str = "above"   # above | below

@dataclass
class EmaFilter:
    enabled: bool = False
    period: int = 9
    condition: str = "above"

@dataclass
class TechnicalFilters:
    rsi: RsiFilter = field(default_factory=RsiFilter)
    sma: SmaFilter = field(default_factory=SmaFilter)
    ema: EmaFilter = field(default_factory=EmaFilter)


# ── Entry Premium / S-L Ratio Filters ────────────────────────────────────────

@dataclass
class EntryPremiumFilter:
    enabled: bool = False
    min_premium: float = 0.0
    max_premium: float = 999.0

@dataclass
class EntrySlRatioFilter:
    enabled: bool = False
    min_ratio: float = 0.0
    max_ratio: float = 999.0


# ── Profit & Loss ─────────────────────────────────────────────────────────────

@dataclass
class ProfitTarget:
    enabled: bool = False
    pt_type: str = "percentage"    # percentage | fixed | closing_order
    target_pct: float = 50.0
    target_fixed: float = 0.0
    closing_price: float = 0.0
    require_two_hits: bool = True

@dataclass
class StopLoss:
    enabled: bool = False
    sl_type: str = "percentage"
    loss_pct: float = 100.0
    loss_fixed: float = 0.0
    closing_price: float = 0.0
    per_leg: bool = False
    trailing_enabled: bool = False
    trailing_trigger_pct: float = 0.0
    trailing_stop_pct: float = 25.0
    trailing_type: str = "recalculated"  # recalculated | fixed
    use_intra_minute: bool = False
    imsl_mode: str = "nbbo"              # nbbo | nbbo_trades
    require_two_hits: bool = False
    breakeven_enabled: bool = False
    breakeven_trigger_pct: float = 20.0


# ── Exit Conditions ───────────────────────────────────────────────────────────

@dataclass
class EarlyExitConfig:
    enabled: bool = False
    exit_type: str = "dte"     # dte | dit | mit
    value: int = 21
    exit_time: str = ""

@dataclass
class UnderlyingMoveExit:
    enabled: bool = False
    unit: str = "pct"
    move_up: float = 0.0
    move_down: float = 0.0

@dataclass
class ShortTestedExit:
    enabled: bool = False
    points_before: float = 0.0

@dataclass
class DeltaExitConfig:
    enabled: bool = False
    use_position_delta: bool = False
    position_delta_below: Optional[float] = None
    position_delta_above: Optional[float] = None
    leg_deltas: List[dict] = field(default_factory=list)

@dataclass
class ShortLongRatioExit:
    enabled: bool = False
    ratio_below: Optional[float] = None
    ratio_above: Optional[float] = None
    pct_move_down: Optional[float] = None
    pct_move_up: Optional[float] = None

@dataclass
class TimeActionItem:
    action_type: str = "dte"     # dte | dit | mit | time
    value: int = 0
    time_str: str = ""
    close_pct: float = 0.0
    adjust_pt: Optional[float] = None
    adjust_sl: Optional[float] = None

@dataclass
class ProfitActionItem:
    trigger_pct: float = 25.0
    close_pct: float = 50.0
    adjust_sl: Optional[float] = None

@dataclass
class ExitConditions:
    early_exit: EarlyExitConfig = field(default_factory=EarlyExitConfig)
    underlying_move: UnderlyingMoveExit = field(default_factory=UnderlyingMoveExit)
    short_tested: ShortTestedExit = field(default_factory=ShortTestedExit)
    delta_exit: DeltaExitConfig = field(default_factory=DeltaExitConfig)
    sl_ratio: ShortLongRatioExit = field(default_factory=ShortLongRatioExit)
    vix_exit: VixFilters = field(default_factory=VixFilters)
    tech_exit: TechnicalFilters = field(default_factory=TechnicalFilters)
    time_actions: List[TimeActionItem] = field(default_factory=list)
    profit_actions: List[ProfitActionItem] = field(default_factory=list)


# ── Misc / Punisher ───────────────────────────────────────────────────────────

@dataclass
class MiscConfig:
    use_commissions: bool = False
    commission_per_contract: float = 0.65
    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    sl_slippage: float = 0.0
    ignore_wide_bid_ask: bool = False
    close_open_trades_on_completion: bool = True
    cap_profits_at_pt: bool = True
    cap_losses_at_sl: bool = False
    require_two_hits_pt: bool = True
    require_two_hits_sl: bool = False


# ── Re-entry ──────────────────────────────────────────────────────────────────

@dataclass
class ReentryConfig:
    enabled: bool = False
    delay_minutes: int = 0
    min_reentry_time: str = "09:32"
    max_reentry_time: str = "15:59"


# ── Entry Frequency / Timing ──────────────────────────────────────────────────

@dataclass
class FrequencyConfig:
    mode: str = "daily"               # daily | weekly | monthly | specific_dates
    weekdays: List[str] = field(default_factory=lambda: ["Mon","Tue","Wed","Thu","Fri"])
    month_days: List[int] = field(default_factory=list)
    specific_dates: str = ""
    use_floating_entry: bool = False
    float_min_time: str = "09:32"
    float_max_time: str = "15:59"
    entry_times: List[str] = field(default_factory=lambda: ["09:45"])
    use_blackout_days: bool = False
    blackout_dates: str = ""


# ── Master Strategy Config ────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    name: str = "My Strategy"
    symbol: str = "SPY"
    port: int = 7497
    client_id: int = 1
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    strike_selection_type: str = "delta"
    round_strikes_multiple: int = 0
    legs: List[LegConfig] = field(default_factory=list)
    preset_strategy: str = "Custom"
    funds: FundsConfig = field(default_factory=FundsConfig)
    frequency: FrequencyConfig = field(default_factory=FrequencyConfig)
    vix: VixFilters = field(default_factory=VixFilters)
    gap: GapFilter = field(default_factory=GapFilter)
    intraday: IntradayMoveFilter = field(default_factory=IntradayMoveFilter)
    squeeze: SqueezeMetricsFilter = field(default_factory=SqueezeMetricsFilter)
    orb: OrbFilter = field(default_factory=OrbFilter)
    technicals: TechnicalFilters = field(default_factory=TechnicalFilters)
    entry_premium: EntryPremiumFilter = field(default_factory=EntryPremiumFilter)
    entry_sl_ratio: EntrySlRatioFilter = field(default_factory=EntrySlRatioFilter)
    profit_target: ProfitTarget = field(default_factory=ProfitTarget)
    stop_loss: StopLoss = field(default_factory=StopLoss)
    exits: ExitConditions = field(default_factory=ExitConditions)
    reentry: ReentryConfig = field(default_factory=ReentryConfig)
    use_leg_groups: bool = False
    entry_execution: EntryExecution = field(default_factory=EntryExecution)
    exit_execution: ExitExecution = field(default_factory=ExitExecution)
    bid_ask_filter: BidAskFilter = field(default_factory=BidAskFilter)
    misc: MiscConfig = field(default_factory=MiscConfig)
    # IBKR live
    trigger_pct: float = 0.005
    window_start: time = time(9, 45)
    window_end: time = time(15, 55)
    entry_time_mode: str = "Window"
    fixed_entry_times: List[str] = field(default_factory=lambda: ["09:45"])