from dataclasses import dataclass, field
from datetime import time
from typing import List, Optional


@dataclass
class FundsAllocation:
    allocation_type: str   = "fixed_quantity"  # percentage | fixed_value | fixed_quantity
    percentage:      float = 5.0
    max_fixed_value: float = 2000.0
    max_contracts:   int   = 1


@dataclass
class StrikeConflict:
    action:            str  = "skip"   # skip | move
    exact_offset_lock: bool = False


@dataclass
class EntryExecution:
    starting_offset:  float = 0.0
    price_adjustment: float = 0.10
    interval_seconds: int   = 10
    max_attempts:     int   = 5
    retry_minutes:    int   = 0

    def __post_init__(self):
        assert self.interval_seconds * self.max_attempts < 55, \
            "interval * max_attempts must be < 55 seconds"


@dataclass
class ExitExecution:
    starting_offset:           float = 0.0
    price_adjustment:          float = 0.10
    interval_seconds:          int   = 10
    max_attempts:              int   = 5
    use_market_after_attempts: bool  = False
    ignore_bidless_longs:      bool  = False


@dataclass
class BidAskFilter:
    enabled:          bool  = False
    mode:             str   = "percentage"   # percentage | fixed
    max_spread_width: float = 0.40
    max_attempts:     int   = 10


@dataclass
class ProfitTargetConfig:
    pt_type: str = "platform"   # platform | resting


@dataclass
class StopLossConfig:
    sl_type:                    str  = "platform"  # platform | intra | resting | oto
    use_intra_minute:           bool = False
    intra_min_consecutive_hits: int  = 1
    use_resting_stop:           bool = False
    use_oto:                    bool = False


@dataclass
class MarketFilters:
    min_vix:            float = 0.0
    max_vix:            float = 999.0
    max_iv:             float = 999.0
    max_spread:         float = 999.0
    min_open_interest:  int   = 0
    require_above_vwap: bool  = False


@dataclass
class StrategyConfig:
    # Core
    symbol:              str   = "SPY"
    trigger_pct:         float = 0.002
    window_start:        time  = time(9, 45)
    window_end:          time  = time(14, 0)
    dte:                 int   = 0
    min_delta:           float = 0.60
    min_confirm_candles: int   = 2
    itm_strikes_deep:    int   = 2
    strike_method:       str   = "delta"

    # Risk
    stop_loss_pct:       float = 0.20
    trailing_stop_pct:   float = 0.15
    profit_target_pct:   float = 0.50
    breakeven_trigger:   float = 0.20
    max_daily_loss:      float = 500.0
    max_trades_per_day:  int   = 1
    max_open_positions:  int   = 1

    # Entry timing
    entry_time_mode:     str         = "Time Window"
    fixed_entry_times:   List[str]   = field(default_factory=list)

    # Broker
    port:      int = 7497
    client_id: int = 1

    # Sub-configs
    funds:          FundsAllocation  = field(default_factory=FundsAllocation)
    strike_conflict:StrikeConflict   = field(default_factory=StrikeConflict)
    entry_execution:EntryExecution   = field(default_factory=EntryExecution)
    exit_execution: ExitExecution    = field(default_factory=ExitExecution)
    bid_ask_filter: BidAskFilter     = field(default_factory=BidAskFilter)
    profit_target:  ProfitTargetConfig = field(default_factory=ProfitTargetConfig)
    stop_loss:      StopLossConfig   = field(default_factory=StopLossConfig)
    market_filters: MarketFilters    = field(default_factory=MarketFilters)

    # Legs raw (for multi-leg future use)
    legs: List[dict] = field(default_factory=list)
