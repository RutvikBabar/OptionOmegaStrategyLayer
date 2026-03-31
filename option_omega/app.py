"""
app.py  —  Option Omega  |  Full Streamlit UI
"""

import streamlit as st
import json
import os
import time
from datetime import datetime, time as dtime

SAVE_FILE = "saved_strategies.json"

st.set_page_config(page_title="Option Omega", layout="wide", page_icon="⚡")

st.markdown("""
<style>
  .block-container { padding-top: 1.2rem; }
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] { padding: 6px 20px; border-radius: 6px; font-weight: 500; }
  .badge { display: inline-block; background: #1e3a5f; color: #90caf9;
           border-radius: 12px; padding: 2px 10px; font-size: 0.75rem; margin: 2px 2px; }
  .badge-green  { background: #14401f; color: #6ee7a0; }
  .badge-red    { background: #4a1a1a; color: #fca5a5; }
  .badge-orange { background: #4a2e00; color: #fdba74; }
  .vix-metric   { font-size: 0.83rem; color: #9ca3af; margin-top: 2px; }
  .section-hdr  { font-weight: 600; font-size: 1rem; color: #e2e8f0; margin: 8px 0 4px 0; }
  .log-line     { font-size: 0.78rem; font-family: monospace;
                  padding: 2px 6px; border-radius: 4px; margin: 1px 0; }
  .log-block    { background: #1a1f2e; border-left: 3px solid #3b82f6; color: #93c5fd; }
  .log-exit     { background: #2d1515; border-left: 3px solid #ef4444; color: #fca5a5; }
  .log-error    { background: #2d1515; border-left: 3px solid #dc2626; color: #f87171; }
  .log-entry    { background: #152d1f; border-left: 3px solid #22c55e; color: #86efac; }
  .log-normal   { color: #d1d5db; }
  .card         { background: #1c1f2e; border-radius: 10px; padding: 14px 18px; margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
UNIT_PCT    = "pct"
UNIT_POINTS = "pts"

STRIKE_METHODS = ["Delta", "Fixed Premium", "Strike Offset", "% OTM"]
STRIKE_METHOD_KEY = {
    "Delta":         "delta",
    "Fixed Premium": "fixed_premium",
    "Strike Offset": "strike_offset",
    "% OTM":         "pct_otm",
}
STRIKE_CAPTIONS = {
    "Delta":         "Nearest strike to the specified delta (e.g. 0.30 = 30Δ).",
    "Fixed Premium": "Nearest strike where the option mid price ≈ target ($).",
    "Strike Offset": "N strikes away from ATM. Positive = OTM, negative = ITM.",
    "% OTM":         "Strike that is X% out-of-the-money from the current underlying.",
}
STRIKE_UNIT = {
    "Delta":         "Δ",
    "Fixed Premium": "$",
    "Strike Offset": "±",
    "% OTM":         "% OTM",
}
STRIKE_DEFAULTS = {
    "Delta":         0.30,
    "Fixed Premium": 1.00,
    "Strike Offset": 0,
    "% OTM":         5.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def safe_float(val, default: float) -> float:
    try:
        return float(str(val).strip())
    except Exception:
        return default


def safe_int(val, default: int) -> int:
    try:
        return int(float(str(val).strip()))
    except Exception:
        return default


def parse_time(val: str, default: str = "09:45") -> str:
    try:
        datetime.strptime(val.strip(), "%H:%M")
        return val.strip()
    except Exception:
        return default


def parse_specific_dates(raw: str) -> list:
    dates = []
    for d in raw.split(","):
        d = d.strip()
        try:
            datetime.strptime(d, "%Y-%m-%d")
            dates.append(d)
        except Exception:
            pass
    return dates


def time_from_str(s: str, default_h: int = 9, default_m: int = 45) -> dtime:
    try:
        parts = s.strip().split(":")
        return dtime(int(parts[0]), int(parts[1]))
    except Exception:
        return dtime(default_h, default_m)


# ─────────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────────
def load_strategies() -> dict:
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_strategies(strategies: dict):
    with open(SAVE_FILE, "w") as f:
        json.dump(strategies, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Session state bootstrap
# ─────────────────────────────────────────────────────────────────────────────
if "saved_strategies" not in st.session_state:
    st.session_state.saved_strategies = load_strategies()
if "deployed" not in st.session_state:
    st.session_state.deployed = {}
if "legs" not in st.session_state:
    st.session_state.legs = []
if "fixed_times" not in st.session_state:
    st.session_state.fixed_times = ["09:45"]
if "brokerage_accounts" not in st.session_state:
    st.session_state.brokerage_accounts = [
        {"label": "IBKR Paper — 7497", "port": 7497, "id": 1},
        {"label": "IBKR Live  — 7496", "port": 7496, "id": 2},
    ]

# ─────────────────────────────────────────────────────────────────────────────
# Leg state helpers
# ─────────────────────────────────────────────────────────────────────────────
MAX_LEGS = 4


def next_leg_id() -> int:
    if not st.session_state.legs:
        return 1
    return max(l["leg_id"] for l in st.session_state.legs) + 1


def get_parent_legs() -> list:
    return [l for l in st.session_state.legs if l["parent_id"] == 0]


def get_child_legs(parent_id: int) -> list:
    return [l for l in st.session_state.legs if l["parent_id"] == parent_id]


def add_parent_leg():
    if len(st.session_state.legs) >= MAX_LEGS:
        return
    st.session_state.legs.append({
        "leg_id":        next_leg_id(),
        "parent_id":     0,
        "action":        "BUY",
        "right":         "CALL",
        "quantity":      "1",
        "strike_method": "delta",
        "strike_val":    "0.30",
        "dte":           "0",
        "exact_dte":     False,
        "lock":          False,
    })


def add_child_leg(parent_id: int):
    if len(st.session_state.legs) >= MAX_LEGS:
        return
    st.session_state.legs.append({
        "leg_id":        next_leg_id(),
        "parent_id":     parent_id,
        "action":        "SELL",
        "right":         "CALL",
        "quantity":      "1",
        "strike_method": "delta",
        "strike_val":    "0.20",
        "dte":           "0",
        "exact_dte":     False,
        "lock":          False,
    })


def delete_leg(leg_id: int):
    st.session_state.legs = [
        l for l in st.session_state.legs
        if l["leg_id"] != leg_id and l["parent_id"] != leg_id
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Leg renderer
# ─────────────────────────────────────────────────────────────────────────────
def render_leg(leg: dict, is_child: bool = False):
    lid      = leg["leg_id"]
    children = get_child_legs(lid)
    has_room = len(st.session_state.legs) < MAX_LEGS

    if "strike_method" not in leg:
        leg["strike_method"] = "delta"

    sm_display = next(
        (k for k, v in STRIKE_METHOD_KEY.items() if v == leg.get("strike_method", "delta")),
        "Delta"
    )

    indent_label = ("↳ Child Leg " + str(lid)) if is_child else ("Leg " + str(lid))

    with st.expander(indent_label, expanded=True):
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1, 1, 1, 1.6, 1.2, 1, 1])

        leg["action"] = c1.selectbox(
            "Action", ["BUY", "SELL"],
            index=["BUY", "SELL"].index(leg.get("action", "BUY")),
            key="leg_action_" + str(lid),
        )
        leg["right"] = c2.selectbox(
            "Right", ["CALL", "PUT"],
            index=["CALL", "PUT"].index(leg.get("right", "CALL")),
            key="leg_right_" + str(lid),
        )
        leg["quantity"] = c3.text_input(
            "Qty", value=leg.get("quantity", "1"),
            key="leg_qty_" + str(lid),
        )

        new_sm_label = c4.selectbox(
            "Strike Method", STRIKE_METHODS,
            index=STRIKE_METHODS.index(sm_display),
            key="leg_sm_" + str(lid),
        )
        if STRIKE_METHOD_KEY[new_sm_label] != leg["strike_method"]:
            leg["strike_method"] = STRIKE_METHOD_KEY[new_sm_label]
            leg["strike_val"]    = str(STRIKE_DEFAULTS[new_sm_label])

        leg["strike_val"] = c5.text_input(
            STRIKE_UNIT.get(new_sm_label, "Val"),
            value=leg.get("strike_val", "0.30"),
            key="leg_sv_" + str(lid),
        )
        leg["dte"] = c6.text_input(
            "DTE", value=leg.get("dte", "0"),
            key="leg_dte_" + str(lid),
        )
        leg["exact_dte"] = c6.checkbox(
            "Exact DTE", value=leg.get("exact_dte", False),
            key="leg_xdte_" + str(lid),
        )
        leg["lock"] = c7.checkbox(
            "Lock Strike", value=leg.get("lock", False),
            key="leg_lock_" + str(lid),
        )

        st.caption(STRIKE_CAPTIONS[new_sm_label])

        btn_cols = st.columns([1, 1, 4])
        if not is_child and has_room:
            if btn_cols[0].button("+ Child Leg", key="add_child_" + str(lid)):
                add_child_leg(lid)
                st.rerun()
        if btn_cols[1].button("Delete", key="del_leg_" + str(lid)):
            delete_leg(lid)
            st.rerun()

    for child in children:
        render_leg(child, is_child=True)


# ─────────────────────────────────────────────────────────────────────────────
# Config builder
# ─────────────────────────────────────────────────────────────────────────────
def build_config_from_params(p: dict):
    from config import (
        StrategyConfig, VixFilters, VixRangeFilter, VixOvernightFilter,
        VixIntradayFilter, Vix9dRatioFilter, GapFilter, IntradayMoveFilter,
        TechnicalFilters, RsiFilter, SmaFilter, EmaFilter,
        EntryExecution, ExitExecution, BidAskFilter,
        ProfitTarget, StopLoss, FundsConfig, RiskConfig,
    )

    vix_filters = VixFilters(
        range=VixRangeFilter(
            enabled = bool(p.get("vix_range_enabled", False)),
            min_vix = safe_float(p.get("vix_min", 0), 0.0),
            max_vix = safe_float(p.get("vix_max", 999), 999.0),
        ),
        overnight=VixOvernightFilter(
            enabled   = bool(p.get("vix_on_enabled", False)),
            direction = p.get("vix_on_dir", "both"),
            unit      = p.get("vix_on_unit", UNIT_PCT),
            threshold = safe_float(p.get("vix_on_thresh", 0), 0.0),
        ),
        intraday=VixIntradayFilter(
            enabled   = bool(p.get("vix_id_enabled", False)),
            direction = p.get("vix_id_dir", "both"),
            unit      = p.get("vix_id_unit", UNIT_PCT),
            min_move  = safe_float(p.get("vix_id_min", 0), 0.0),
            max_move  = safe_float(p.get("vix_id_max", 999), 999.0),
        ),
        vix9d=Vix9dRatioFilter(
            enabled         = bool(p.get("vix9d_enabled", False)),
            entry_min_ratio = safe_float(p.get("vix9d_entry_min", 0), 0.0),
            entry_max_ratio = safe_float(p.get("vix9d_entry_max", 999), 999.0),
            use_exit        = bool(p.get("vix9d_use_exit", False)),
            exit_min_ratio  = safe_float(p.get("vix9d_exit_min", 0), 0.0),
            exit_max_ratio  = safe_float(p.get("vix9d_exit_max", 999), 999.0),
        ),
    )

    gap = GapFilter(
        enabled   = bool(p.get("gap_enabled", False)),
        direction = p.get("gap_dir", "both"),
        unit      = p.get("gap_unit", UNIT_PCT),
        min_gap   = safe_float(p.get("gap_min", 0), 0.0),
        max_gap   = safe_float(p.get("gap_max", 999), 999.0),
    )
    intraday_move = IntradayMoveFilter(
        enabled   = bool(p.get("id_enabled", False)),
        direction = p.get("id_dir", "both"),
        unit      = p.get("id_unit", UNIT_PCT),
        min_move  = safe_float(p.get("id_min", 0), 0.0),
        max_move  = safe_float(p.get("id_max", 999), 999.0),
    )
    technicals = TechnicalFilters(
        rsi=RsiFilter(
            enabled = bool(p.get("rsi_enabled", False)),
            period  = safe_int(p.get("rsi_period", 14), 14),
            min_rsi = safe_float(p.get("rsi_min", 0), 0.0),
            max_rsi = safe_float(p.get("rsi_max", 100), 100.0),
        ),
        sma=SmaFilter(
            enabled   = bool(p.get("sma_enabled", False)),
            period    = safe_int(p.get("sma_period", 20), 20),
            condition = p.get("sma_cond", "above"),
        ),
        ema=EmaFilter(
            enabled   = bool(p.get("ema_enabled", False)),
            period    = safe_int(p.get("ema_period", 9), 9),
            condition = p.get("ema_cond", "above"),
        ),
    )

    entry_exec = EntryExecution(
        max_attempts              = safe_int(p.get("entry_max_att", 5), 5),
        retry_minutes             = safe_int(p.get("entry_retry_min", 0), 0),
        starting_offset           = safe_float(p.get("entry_start_off", 0.0), 0.0),
        price_adjustment          = safe_float(p.get("entry_price_adj", 0.05), 0.05),
        interval_seconds          = safe_int(p.get("entry_interval", 30), 30),
        use_market_after_attempts = bool(p.get("entry_use_mkt", True)),
    )
    exit_exec = ExitExecution(
        max_attempts              = safe_int(p.get("exit_max_att", 5), 5),
        starting_offset           = safe_float(p.get("exit_start_off", 0.0), 0.0),
        price_adjustment          = safe_float(p.get("exit_price_adj", 0.05), 0.05),
        interval_seconds          = safe_int(p.get("exit_interval", 30), 30),
        use_market_after_attempts = bool(p.get("exit_use_mkt", True)),
        ignore_bidless_longs      = bool(p.get("exit_ignore_bidless", False)),
    )
    ba_filter = BidAskFilter(
        enabled          = bool(p.get("ba_enabled", False)),
        mode             = p.get("ba_mode", "percentage"),
        max_spread_width = safe_float(p.get("ba_max_spread", 0.10), 0.10),
        max_attempts     = safe_int(p.get("ba_max_att", 3), 3),
    )
    profit_target = ProfitTarget(
        pt_type    = p.get("pt_type", "platform"),
        target_pct = safe_float(p.get("pt_pct", 0.50), 0.50),
    )
    stop_loss = StopLoss(
        sl_type                    = p.get("sl_type", "platform"),
        loss_pct                   = safe_float(p.get("sl_pct", 0.50), 0.50),
        use_resting_stop           = bool(p.get("sl_resting", False)),
        use_oto                    = bool(p.get("sl_oto", False)),
        trailing_enabled           = bool(p.get("sl_trailing", False)),
        trailing_trigger_pct       = safe_float(p.get("sl_trail_trigger", 0.20), 0.20),
        trailing_stop_pct          = safe_float(p.get("sl_trail_stop", 0.10), 0.10),
        breakeven_enabled          = bool(p.get("sl_breakeven", False)),
        breakeven_trigger_pct      = safe_float(p.get("sl_be_trigger", 0.15), 0.15),
        intra_min_consecutive_hits = safe_int(p.get("sl_intra_hits", 3), 3),
    )
    funds = FundsConfig(
        allocation_type = p.get("funds_type", "fixed_value"),
        max_fixed_value = safe_float(p.get("funds_fixed_val", 5000.0), 5000.0),
        max_contracts   = safe_int(p.get("funds_max_qty", 10), 10),
        percentage      = safe_float(p.get("funds_pct", 10.0), 10.0),
    )
    risk = RiskConfig(
        max_daily_loss     = safe_float(p.get("risk_daily_loss", 500.0), 500.0),
        max_trades_per_day = safe_int(p.get("risk_max_trades", 3), 3),
        max_open_positions = safe_int(p.get("risk_max_pos", 1), 1),
    )

    ws = time_from_str(p.get("window_start", "09:45"), 9, 45)
    we = time_from_str(p.get("window_end",   "15:55"), 15, 55)

    return StrategyConfig(
        name              = p.get("name", "Strategy"),
        symbol            = p.get("symbol", "SPY"),
        client_id         = safe_int(p.get("client_id", 1), 1),
        port              = safe_int(p.get("port", 7497), 7497),
        entry_time_mode   = p.get("entry_time_mode", "Window"),
        window_start      = ws,
        window_end        = we,
        fixed_entry_times = p.get("fixed_entry_times", ["09:45"]),
        trigger_pct       = safe_float(p.get("trigger_pct", 0.005), 0.005),
        min_delta         = safe_float(p.get("min_delta", 0.30), 0.30),
        strike_method     = p.get("strike_method", "delta"),
        dte               = safe_int(p.get("dte", 0), 0),
        legs              = p.get("legs", []),
        vix               = vix_filters,
        gap               = gap,
        intraday          = intraday_move,
        technicals        = technicals,
        entry_execution   = entry_exec,
        exit_execution    = exit_exec,
        bid_ask_filter    = ba_filter,
        profit_target     = profit_target,
        stop_loss         = stop_loss,
        funds             = funds,
        risk              = risk,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Active filter badge builder
# ─────────────────────────────────────────────────────────────────────────────
def get_active_filter_badges(data: dict) -> list:
    badges = []
    if data.get("vix_range_enabled"):
        badges.append("VIX [" + str(data.get("vix_min", 0)) + "-" + str(data.get("vix_max", 999)) + "]")
    if data.get("vix_on_enabled"):
        unit = "%" if data.get("vix_on_unit") == UNIT_PCT else "pts"
        badges.append("VIX-ON " + str(data.get("vix_on_dir", "?")) + " >=" + str(round(safe_float(data.get("vix_on_thresh", 0), 0), 2)) + unit)
    if data.get("vix_id_enabled"):
        unit = "%" if data.get("vix_id_unit") == UNIT_PCT else "pts"
        badges.append("VIX-ID [" + str(round(safe_float(data.get("vix_id_min", 0), 0), 2)) + "-" + str(round(safe_float(data.get("vix_id_max", 999), 999), 1)) + "]" + unit)
    if data.get("vix9d_enabled"):
        badges.append("VIX9D ratio [" + str(round(safe_float(data.get("vix9d_entry_min", 0), 0), 3)) + "-" + str(round(safe_float(data.get("vix9d_entry_max", 999), 999), 3)) + "]")
    if data.get("gap_enabled"):
        unit = "%" if data.get("gap_unit") == UNIT_PCT else "pts"
        badges.append("GAP " + str(data.get("gap_dir", "?")) + " " + unit)
    if data.get("id_enabled"):
        unit = "%" if data.get("id_unit") == UNIT_PCT else "pts"
        badges.append("ID " + str(data.get("id_dir", "?")) + " " + unit)
    if data.get("rsi_enabled"):
        badges.append("RSI [" + str(round(safe_float(data.get("rsi_min", 0), 0), 0)) + "-" + str(round(safe_float(data.get("rsi_max", 100), 100), 0)) + "]")
    if data.get("sma_enabled"):
        badges.append("SMA-" + str(safe_int(data.get("sma_period", 20), 20)) + " " + str(data.get("sma_cond", "above")))
    if data.get("ema_enabled"):
        badges.append("EMA-" + str(safe_int(data.get("ema_period", 9), 9)) + " " + str(data.get("ema_cond", "above")))
    return badges


# ─────────────────────────────────────────────────────────────────────────────
# Page header + tabs
# ─────────────────────────────────────────────────────────────────────────────
st.title("Option Omega")
tabs = st.tabs(["Strategy Builder", "Live Dashboard", "Trade Log"])


# =============================================================================
# TAB 1 — STRATEGY BUILDER
# =============================================================================
with tabs[0]:
    sidebar_col, form_col = st.columns([1, 3], gap="medium")

    # ── Saved strategy list ───────────────────────────────────────────────────
    with sidebar_col:
        st.markdown("### Saved Strategies")
        saved = st.session_state.saved_strategies

        if not saved:
            st.info("No saved strategies yet.")
        else:
            for sname, sdata in list(saved.items()):
                is_live    = sname in st.session_state.deployed
                live_badge = "Live" if is_live else "Idle"
                st.markdown("**" + sname + "** — " + live_badge)
                st.caption("Symbol: " + sdata.get("symbol", "?"))

                b1, b2, b3 = st.columns(3)
                if b1.button("Load", key="load_" + sname):
                    st.session_state["_loaded"] = sdata
                    st.session_state.legs = sdata.get("legs", [])
                    st.rerun()
                if b2.button("Delete", key="del_" + sname):
                    del st.session_state.saved_strategies[sname]
                    save_strategies(st.session_state.saved_strategies)
                    st.rerun()
                if not is_live:
                    if b3.button("Deploy", key="dep_" + sname):
                        st.session_state.deployed[sname] = {
                            "started":      datetime.now().strftime("%H:%M:%S"),
                            "data":         sdata,
                            "strategy_obj": None,
                        }
                        st.success(sname + " deployed!")
                        st.rerun()
                else:
                    if b3.button("Stop", key="stop_" + sname):
                        obj = st.session_state.deployed[sname].get("strategy_obj")
                        if obj and hasattr(obj, "stop"):
                            obj.stop()
                        del st.session_state.deployed[sname]
                        st.info(sname + " stopped.")
                        st.rerun()
                st.divider()

    # ── Builder form ──────────────────────────────────────────────────────────
    with form_col:
        loaded = st.session_state.pop("_loaded", None)

        st.markdown("### Strategy Configuration")

        id_row = st.columns(4)
        strat_name = id_row[0].text_input(
            "Strategy Name",
            value=loaded.get("name", "My Strategy") if loaded else "My Strategy",
        )
        symbol = id_row[1].text_input(
            "Symbol",
            value=loaded.get("symbol", "SPY") if loaded else "SPY",
        ).upper().strip()

        acct_labels   = [a["label"] for a in st.session_state.brokerage_accounts]
        selected_acct = id_row[2].selectbox("Brokerage Account", acct_labels)
        acct_obj      = next(
            a for a in st.session_state.brokerage_accounts
            if a["label"] == selected_acct
        )

        trigger_pct = safe_float(
            id_row[3].text_input(
                "Trigger % (e.g. 0.005)",
                value=str(loaded.get("trigger_pct", "0.005")) if loaded else "0.005",
            ),
            0.005,
        )

        # ── Entry Timing ──────────────────────────────────────────────────────
        with st.expander("Entry Timing", expanded=False):
            time_mode = st.radio(
                "Entry Mode",
                ["Window", "Fixed Entry Times"],
                horizontal=True,
                index=0 if not loaded else
                      (1 if loaded.get("entry_time_mode") == "Fixed Entry Times" else 0),
            )
            if time_mode == "Window":
                tc1, tc2 = st.columns(2)
                w_start = tc1.text_input(
                    "Window Start (HH:MM)",
                    value=loaded.get("window_start", "09:45") if loaded else "09:45",
                )
                w_end = tc2.text_input(
                    "Window End (HH:MM)",
                    value=loaded.get("window_end", "15:55") if loaded else "15:55",
                )
                fixed_entry_times = loaded.get("fixed_entry_times", ["09:45"]) if loaded else ["09:45"]
            else:
                default_ft = "\n".join(loaded.get("fixed_entry_times", ["09:45"]) if loaded else ["09:45"])
                ft_raw = st.text_area(
                    "Times (HH:MM one per line)",
                    value=default_ft,
                    height=90,
                )
                fixed_entry_times = [
                    parse_time(t.strip())
                    for t in ft_raw.replace(",", "\n").split("\n")
                    if t.strip()
                ]
                w_start = "09:45"
                w_end   = "15:55"

        # ── Legs ─────────────────────────────────────────────────────────────
        with st.expander("Legs", expanded=True):
            if len(st.session_state.legs) < MAX_LEGS:
                if st.button("+ Add Leg"):
                    add_parent_leg()
                    st.rerun()
            else:
                st.caption("Maximum " + str(MAX_LEGS) + " legs reached.")

            for leg in get_parent_legs():
                render_leg(leg, is_child=False)

        # ── VIX Filters ───────────────────────────────────────────────────────
        with st.expander("VIX Filters", expanded=False):

            # VIX Range
            st.markdown('<div class="section-hdr">VIX Range</div>', unsafe_allow_html=True)
            vix_range_enabled = st.checkbox("Enable VIX Range Filter",
                value=bool(loaded.get("vix_range_enabled", False)) if loaded else False,
                key="vix_range_enabled")
            if vix_range_enabled:
                rc1, rc2 = st.columns(2)
                vix_min = rc1.number_input("Min VIX", min_value=0.0, max_value=500.0,
                    value=safe_float(loaded.get("vix_min", 0.0) if loaded else 0.0, 0.0),
                    step=0.5, format="%.1f", key="vix_min_input")
                vix_max = rc2.number_input("Max VIX", min_value=0.0, max_value=500.0,
                    value=safe_float(loaded.get("vix_max", 999.0) if loaded else 999.0, 999.0),
                    step=0.5, format="%.1f", key="vix_max_input")
                st.caption("Entry allowed when VIX is between " + str(vix_min) + " and " + str(vix_max) + ".")
            else:
                vix_min, vix_max = 0.0, 999.0

            st.divider()

            # VIX Overnight
            st.markdown('<div class="section-hdr">VIX Overnight Move</div>', unsafe_allow_html=True)
            vix_on_enabled = st.checkbox("Enable VIX Overnight Filter",
                value=bool(loaded.get("vix_on_enabled", False)) if loaded else False,
                key="vix_on_enabled")
            if vix_on_enabled:
                oc1, oc2, oc3, oc4 = st.columns(4)
                vix_on_dir = oc1.selectbox("Direction", ["up", "down", "both"],
                    index=["up", "down", "both"].index(loaded.get("vix_on_dir", "both") if loaded else "both"),
                    key="vix_on_dir")
                vix_on_unit = oc2.selectbox("Unit", [UNIT_PCT, UNIT_POINTS],
                    index=0 if not loaded or loaded.get("vix_on_unit") == UNIT_PCT else 1,
                    key="vix_on_unit")
                vix_on_thresh = oc3.number_input("Min Move Threshold", min_value=0.0,
                    value=safe_float(loaded.get("vix_on_thresh", 0.0) if loaded else 0.0, 0.0),
                    step=0.1, format="%.2f", key="vix_on_thresh")
                unit_lbl = "%" if vix_on_unit == UNIT_PCT else " pts"
                oc4.caption("Compares last pre-market VIX snap (before 09:25) to current VIX. Requires |move| >= " + str(vix_on_thresh) + unit_lbl + ", direction = " + vix_on_dir + ".")
            else:
                vix_on_dir, vix_on_unit, vix_on_thresh = "both", UNIT_PCT, 0.0

            st.divider()

            # VIX Intraday
            st.markdown('<div class="section-hdr">VIX Intraday Move</div>', unsafe_allow_html=True)
            vix_id_enabled = st.checkbox("Enable VIX Intraday Filter",
                value=bool(loaded.get("vix_id_enabled", False)) if loaded else False,
                key="vix_id_enabled")
            if vix_id_enabled:
                ic1, ic2, ic3, ic4, ic5 = st.columns(5)
                vix_id_dir = ic1.selectbox("Direction", ["up", "down", "both"],
                    index=["up", "down", "both"].index(loaded.get("vix_id_dir", "both") if loaded else "both"),
                    key="vix_id_dir")
                vix_id_unit = ic2.selectbox("Unit", [UNIT_PCT, UNIT_POINTS],
                    index=0 if not loaded or loaded.get("vix_id_unit") == UNIT_PCT else 1,
                    key="vix_id_unit")
                vix_id_min = ic3.number_input("Min Move", min_value=0.0,
                    value=safe_float(loaded.get("vix_id_min", 0.0) if loaded else 0.0, 0.0),
                    step=0.1, format="%.2f", key="vix_id_min")
                vix_id_max = ic4.number_input("Max Move", min_value=0.0,
                    value=safe_float(loaded.get("vix_id_max", 999.0) if loaded else 999.0, 999.0),
                    step=0.5, format="%.2f", key="vix_id_max")
                id_unit_lbl = "%" if vix_id_unit == UNIT_PCT else " pts"
                ic5.caption("VIX RTH open (09:25 print) to current 1-min bar open. Range [" + str(vix_id_min) + ", " + str(vix_id_max) + "]" + id_unit_lbl + " dir=" + vix_id_dir + ".")
            else:
                vix_id_dir, vix_id_unit = "both", UNIT_PCT
                vix_id_min, vix_id_max  = 0.0, 999.0

            st.divider()

            # VIX9D / VIX Ratio
            st.markdown('<div class="section-hdr">VIX9D / VIX Ratio</div>', unsafe_allow_html=True)
            vix9d_enabled = st.checkbox("Enable VIX9D / VIX Ratio Filter",
                value=bool(loaded.get("vix9d_enabled", False)) if loaded else False,
                key="vix9d_enabled")
            if vix9d_enabled:
                r1, r2 = st.columns(2)
                vix9d_entry_min = r1.number_input("Entry Min Ratio", min_value=0.0,
                    value=safe_float(loaded.get("vix9d_entry_min", 0.0) if loaded else 0.0, 0.0),
                    step=0.01, format="%.3f", key="vix9d_entry_min")
                vix9d_entry_max = r2.number_input("Entry Max Ratio", min_value=0.0,
                    value=safe_float(loaded.get("vix9d_entry_max", 999.0) if loaded else 999.0, 999.0),
                    step=0.01, format="%.3f", key="vix9d_entry_max")
                st.caption("If VIX9D has not printed by entry time, entry is BLOCKED. Ratio = VIX9D / VIX using open of current 1-min bar.")

                vix9d_use_exit = st.checkbox(
                    "Use a separate VIX9D/VIX exit condition",
                    value=bool(loaded.get("vix9d_use_exit", False)) if loaded else False,
                    key="vix9d_use_exit")
                if vix9d_use_exit:
                    ex1, ex2 = st.columns(2)
                    vix9d_exit_min = ex1.number_input("Exit Min Ratio", min_value=0.0,
                        value=safe_float(loaded.get("vix9d_exit_min", 0.0) if loaded else 0.0, 0.0),
                        step=0.01, format="%.3f", key="vix9d_exit_min")
                    vix9d_exit_max = ex2.number_input("Exit Max Ratio", min_value=0.0,
                        value=safe_float(loaded.get("vix9d_exit_max", 999.0) if loaded else 999.0, 999.0),
                        step=0.01, format="%.3f", key="vix9d_exit_max")
                    st.caption("If VIX9D has not printed, the exit condition is skipped (non-blocking).")
                else:
                    vix9d_exit_min, vix9d_exit_max = 0.0, 999.0
            else:
                vix9d_entry_min, vix9d_entry_max = 0.0, 999.0
                vix9d_use_exit                   = False
                vix9d_exit_min, vix9d_exit_max   = 0.0, 999.0

        # ── Underlying Filters ─────────────────────────────────────────────────
        with st.expander("Underlying Filters", expanded=False):

            # Gap
            st.markdown('<div class="section-hdr">Overnight Gap</div>', unsafe_allow_html=True)
            gap_enabled = st.checkbox("Enable Gap Filter",
                value=bool(loaded.get("gap_enabled", False)) if loaded else False,
                key="gap_enabled")
            if gap_enabled:
                g1, g2, g3, g4, g5 = st.columns(5)
                gap_dir  = g1.selectbox("Direction", ["up", "down", "both"], key="gap_dir")
                gap_unit = g2.selectbox("Unit", [UNIT_PCT, UNIT_POINTS], key="gap_unit")
                gap_min  = g3.number_input("Min Gap", min_value=0.0, step=0.1, format="%.2f", key="gap_min")
                gap_max  = g4.number_input("Max Gap", min_value=0.0, value=999.0, step=0.5, format="%.2f", key="gap_max")
                g5.caption("Prev close to RTH open. Direction controls sign.")
            else:
                gap_dir, gap_unit = "both", UNIT_PCT
                gap_min, gap_max  = 0.0, 999.0

            st.divider()

            # Intraday Move
            st.markdown('<div class="section-hdr">Intraday Move</div>', unsafe_allow_html=True)
            id_enabled = st.checkbox("Enable Intraday Move Filter",
                value=bool(loaded.get("id_enabled", False)) if loaded else False,
                key="id_enabled")
            if id_enabled:
                im1, im2, im3, im4, im5 = st.columns(5)
                id_dir  = im1.selectbox("Direction", ["up", "down", "both"], key="id_dir")
                id_unit = im2.selectbox("Unit", [UNIT_PCT, UNIT_POINTS], key="id_unit")
                id_min  = im3.number_input("Min Move", min_value=0.0, step=0.1, format="%.2f", key="id_min")
                id_max  = im4.number_input("Max Move", min_value=0.0, value=999.0, step=0.5, format="%.2f", key="id_max")
                im5.caption("Daily open (1-min candle open) to current price. Updated every minute.")
            else:
                id_dir, id_unit = "both", UNIT_PCT
                id_min, id_max  = 0.0, 999.0

            st.divider()

            # RSI
            st.markdown('<div class="section-hdr">RSI</div>', unsafe_allow_html=True)
            rsi_enabled = st.checkbox("Enable RSI Filter",
                value=bool(loaded.get("rsi_enabled", False)) if loaded else False,
                key="rsi_enabled")
            if rsi_enabled:
                ri1, ri2, ri3, ri4 = st.columns(4)
                rsi_period = safe_int(ri1.number_input("Period", min_value=2, max_value=100, value=14, key="rsi_period"), 14)
                rsi_min    = ri2.number_input("Min RSI", min_value=0.0, max_value=100.0, value=0.0, step=1.0, key="rsi_min")
                rsi_max    = ri3.number_input("Max RSI", min_value=0.0, max_value=100.0, value=100.0, step=1.0, key="rsi_max")
                ri4.caption("Wilder RSI-14. Updated per minute using last (N-1) daily closes + current intraday price.")
            else:
                rsi_period, rsi_min, rsi_max = 14, 0.0, 100.0

            st.divider()

            # SMA
            st.markdown('<div class="section-hdr">SMA</div>', unsafe_allow_html=True)
            sma_enabled = st.checkbox("Enable SMA Filter",
                value=bool(loaded.get("sma_enabled", False)) if loaded else False,
                key="sma_enabled")
            if sma_enabled:
                sm1, sm2, sm3 = st.columns(3)
                sma_period = safe_int(sm1.number_input("SMA Period", min_value=2, max_value=500, value=20, key="sma_period"), 20)
                sma_cond   = sm2.selectbox("Price must be", ["above", "below"], key="sma_cond")
                sm3.caption("Daily resolution: last (N-1) closes + current intraday price.")
            else:
                sma_period, sma_cond = 20, "above"

            st.divider()

            # EMA
            st.markdown('<div class="section-hdr">EMA</div>', unsafe_allow_html=True)
            ema_enabled = st.checkbox("Enable EMA Filter",
                value=bool(loaded.get("ema_enabled", False)) if loaded else False,
                key="ema_enabled")
            if ema_enabled:
                em1, em2, em3 = st.columns(3)
                ema_period = safe_int(em1.number_input("EMA Period", min_value=2, max_value=200, value=9, key="ema_period"), 9)
                ema_cond   = em2.selectbox("Price must be", ["above", "below"], key="ema_cond")
                em3.caption("Intraday 1-minute bars (full deque including extended hours).")
            else:
                ema_period, ema_cond = 9, "above"

        # ── Execution ──────────────────────────────────────────────────────────
        with st.expander("Execution", expanded=False):

            st.markdown('<div class="section-hdr">Entry Execution</div>', unsafe_allow_html=True)
            ec1, ec2, ec3, ec4, ec5 = st.columns(5)
            entry_max_att   = safe_int(ec1.number_input("Max Attempts", min_value=1, value=5, key="entry_max_att"), 5)
            entry_retry_min = safe_int(ec2.number_input("Retry Window (min)", min_value=0, value=0, key="entry_retry_min"), 0)
            entry_start_off = ec3.number_input("Start Offset ($)", value=0.0, step=0.01, format="%.2f", key="entry_start_off")
            entry_price_adj = ec4.number_input("Price Adj ($)", value=0.05, step=0.01, format="%.2f", key="entry_price_adj")
            entry_interval  = safe_int(ec5.number_input("Interval (s)", min_value=1, value=30, key="entry_interval"), 30)
            entry_use_mkt   = st.checkbox("Convert to market order after max entry attempts", value=True, key="entry_use_mkt")
            st.caption("Retry Window > 0: resets to fresh mid after max attempts and keeps retrying until window expires. = 0: converts to market order immediately.")

            st.divider()
            st.markdown('<div class="section-hdr">Exit Execution</div>', unsafe_allow_html=True)
            xc1, xc2, xc3, xc4, xc5 = st.columns(5)
            exit_max_att        = safe_int(xc1.number_input("Max Attempts", min_value=1, value=5, key="exit_max_att"), 5)
            exit_start_off      = xc2.number_input("Start Offset ($)", value=0.0, step=0.01, format="%.2f", key="exit_start_off")
            exit_price_adj      = xc3.number_input("Price Adj ($)", value=0.05, step=0.01, format="%.2f", key="exit_price_adj")
            exit_interval       = safe_int(xc4.number_input("Interval (s)", min_value=1, value=30, key="exit_interval"), 30)
            exit_use_mkt        = xc5.checkbox("Market after max attempts", value=True, key="exit_use_mkt")
            exit_ignore_bidless = st.checkbox("Ignore bidless longs on exit", key="exit_ignore_bidless")
            st.caption("Market After = OFF: resets to current mid at top of next minute and retries indefinitely.")

            st.divider()
            st.markdown('<div class="section-hdr">Bid-Ask Spread Guard</div>', unsafe_allow_html=True)
            ba_enabled = st.checkbox("Enable Bid-Ask Spread Filter", key="ba_enabled")
            if ba_enabled:
                ba1, ba2, ba3, ba4 = st.columns(4)
                ba_mode       = ba1.selectbox("Mode", ["percentage", "points"], key="ba_mode")
                ba_max_spread = ba2.number_input("Max Spread", min_value=0.0, value=0.10, step=0.01, format="%.2f", key="ba_max_spread")
                ba_max_att    = safe_int(ba3.number_input("Max Skip Attempts", min_value=1, value=3, key="ba_max_att"), 3)
                ba4.caption("Checked before each exit attempt. After max skips, exit is forced regardless of spread.")
            else:
                ba_mode, ba_max_spread, ba_max_att = "percentage", 0.10, 3

        # ── Risk & P&L ─────────────────────────────────────────────────────────
        with st.expander("Risk & P&L", expanded=False):

            st.markdown('<div class="section-hdr">Profit Target</div>', unsafe_allow_html=True)
            pt1, pt2, pt3 = st.columns(3)
            pt_type = pt1.selectbox("Type", ["platform", "resting"], key="pt_type")
            pt_pct  = pt2.number_input("Target % of entry", min_value=0.0, max_value=100.0,
                          value=50.0, step=5.0, format="%.1f", key="pt_pct") / 100.0
            pt3.caption("platform = checked every second. resting = submitted as a resting limit order at entry.")

            st.divider()
            st.markdown('<div class="section-hdr">Stop Loss</div>', unsafe_allow_html=True)
            sl1, sl2, sl3, sl4 = st.columns(4)
            sl_type    = sl1.selectbox("Type", ["platform", "resting", "oto"], key="sl_type")
            sl_pct     = sl2.number_input("Stop Loss % of entry", min_value=0.0, max_value=100.0,
                             value=50.0, step=5.0, format="%.1f", key="sl_pct") / 100.0
            sl_resting = sl3.checkbox("Resting Stop Order", key="sl_resting")
            sl_oto     = sl4.checkbox("OTO (One-Triggers-Other)", key="sl_oto")

            st.markdown("**Trailing Stop**")
            tr1, tr2, tr3 = st.columns(3)
            sl_trailing      = tr1.checkbox("Enable Trailing Stop", key="sl_trailing")
            sl_trail_trigger = tr2.number_input("Trigger Gain %", min_value=0.0, value=20.0,
                                   step=1.0, format="%.1f", key="sl_trail_trigger",
                                   disabled=not sl_trailing) / 100.0
            sl_trail_stop    = tr3.number_input("Trail Distance %", min_value=0.0, value=10.0,
                                   step=1.0, format="%.1f", key="sl_trail_stop",
                                   disabled=not sl_trailing) / 100.0

            st.markdown("**Breakeven**")
            be1, be2, be3 = st.columns(3)
            sl_breakeven  = be1.checkbox("Enable Breakeven", key="sl_breakeven")
            sl_be_trigger = be2.number_input("Breakeven Trigger %", min_value=0.0, value=15.0,
                               step=1.0, format="%.1f", key="sl_be_trigger",
                               disabled=not sl_breakeven) / 100.0
            be3.caption("Once gain >= trigger, stop loss is moved to entry price. One-time per trade.")

            st.markdown("**Intra-Minute Stop**")
            im_c1, im_c2 = st.columns(2)
            sl_intra_hits = safe_int(im_c1.number_input("Consecutive hits to trigger", min_value=1, value=3, key="sl_intra_hits"), 3)
            im_c2.caption("Stop checked every second. N consecutive ticks below stop price before firing.")

            st.divider()
            st.markdown('<div class="section-hdr">Position Sizing</div>', unsafe_allow_html=True)
            fs1, fs2 = st.columns(2)
            funds_type = fs1.selectbox("Allocation Type",
                ["fixed_value", "fixed_quantity", "percentage"], key="funds_type")
            funds_fixed_val = 5000.0
            funds_max_qty   = 10
            funds_pct       = 10.0
            if funds_type == "fixed_value":
                funds_fixed_val = fs2.number_input("Max $ per Trade", min_value=0.0,
                    value=5000.0, step=100.0, key="funds_fixed_val")
            elif funds_type == "fixed_quantity":
                funds_max_qty = safe_int(fs2.number_input("Max Contracts", min_value=1,
                    value=10, key="funds_max_qty"), 10)
            else:
                funds_pct = fs2.number_input("% of Account NLV", min_value=0.1,
                    max_value=100.0, value=10.0, step=0.5, key="funds_pct")

            st.divider()
            st.markdown('<div class="section-hdr">Daily Risk Limits</div>', unsafe_allow_html=True)
            dr1, dr2, dr3 = st.columns(3)
            risk_daily_loss = dr1.number_input("Max Daily Loss ($)", min_value=0.0,
                value=500.0, step=50.0, key="risk_daily_loss")
            risk_max_trades = safe_int(dr2.number_input("Max Trades / Day", min_value=1,
                value=3, key="risk_max_trades"), 3)
            risk_max_pos    = safe_int(dr3.number_input("Max Open Positions", min_value=1,
                value=1, key="risk_max_pos"), 1)

        # ── Save / Deploy buttons ──────────────────────────────────────────────
        st.divider()
        btn1, btn2, btn3 = st.columns(3)

        def _collect_params():
            return {
                "name":               strat_name,
                "symbol":             symbol,
                "client_id":          acct_obj["id"],
                "port":               acct_obj["port"],
                "trigger_pct":        trigger_pct,
                "entry_time_mode":    time_mode,
                "window_start":       w_start,
                "window_end":         w_end,
                "fixed_entry_times":  fixed_entry_times,
                "legs":               st.session_state.legs,
                # VIX
                "vix_range_enabled":  vix_range_enabled,
                "vix_min":            vix_min,
                "vix_max":            vix_max,
                "vix_on_enabled":     vix_on_enabled,
                "vix_on_dir":         vix_on_dir,
                "vix_on_unit":        vix_on_unit,
                "vix_on_thresh":      vix_on_thresh,
                "vix_id_enabled":     vix_id_enabled,
                "vix_id_dir":         vix_id_dir,
                "vix_id_unit":        vix_id_unit,
                "vix_id_min":         vix_id_min,
                "vix_id_max":         vix_id_max,
                "vix9d_enabled":      vix9d_enabled,
                "vix9d_entry_min":    vix9d_entry_min,
                "vix9d_entry_max":    vix9d_entry_max,
                "vix9d_use_exit":     vix9d_use_exit,
                "vix9d_exit_min":     vix9d_exit_min,
                "vix9d_exit_max":     vix9d_exit_max,
                # Underlying filters
                "gap_enabled":        gap_enabled,
                "gap_dir":            gap_dir,
                "gap_unit":           gap_unit,
                "gap_min":            gap_min,
                "gap_max":            gap_max,
                "id_enabled":         id_enabled,
                "id_dir":             id_dir,
                "id_unit":            id_unit,
                "id_min":             id_min,
                "id_max":             id_max,
                "rsi_enabled":        rsi_enabled,
                "rsi_period":         rsi_period,
                "rsi_min":            rsi_min,
                "rsi_max":            rsi_max,
                "sma_enabled":        sma_enabled,
                "sma_period":         sma_period,
                "sma_cond":           sma_cond,
                "ema_enabled":        ema_enabled,
                "ema_period":         ema_period,
                "ema_cond":           ema_cond,
                # Execution
                "entry_max_att":      entry_max_att,
                "entry_retry_min":    entry_retry_min,
                "entry_start_off":    entry_start_off,
                "entry_price_adj":    entry_price_adj,
                "entry_interval":     entry_interval,
                "entry_use_mkt":      entry_use_mkt,
                "exit_max_att":       exit_max_att,
                "exit_start_off":     exit_start_off,
                "exit_price_adj":     exit_price_adj,
                "exit_interval":      exit_interval,
                "exit_use_mkt":       exit_use_mkt,
                "exit_ignore_bidless": exit_ignore_bidless,
                "ba_enabled":         ba_enabled,
                "ba_mode":            ba_mode,
                "ba_max_spread":      ba_max_spread,
                "ba_max_att":         ba_max_att,
                # P&L / risk
                "pt_type":            pt_type,
                "pt_pct":             pt_pct,
                "sl_type":            sl_type,
                "sl_pct":             sl_pct,
                "sl_resting":         sl_resting,
                "sl_oto":             sl_oto,
                "sl_trailing":        sl_trailing,
                "sl_trail_trigger":   sl_trail_trigger,
                "sl_trail_stop":      sl_trail_stop,
                "sl_breakeven":       sl_breakeven,
                "sl_be_trigger":      sl_be_trigger,
                "sl_intra_hits":      sl_intra_hits,
                "funds_type":         funds_type,
                "funds_fixed_val":    funds_fixed_val,
                "funds_max_qty":      funds_max_qty,
                "funds_pct":          funds_pct,
                "risk_daily_loss":    risk_daily_loss,
                "risk_max_trades":    risk_max_trades,
                "risk_max_pos":       risk_max_pos,
            }

        if btn1.button("Save Strategy"):
            params = _collect_params()
            st.session_state.saved_strategies[strat_name] = params
            save_strategies(st.session_state.saved_strategies)
            st.success("Strategy '" + strat_name + "' saved!")
            st.rerun()

        if btn2.button("Save & Deploy"):
            params = _collect_params()
            st.session_state.saved_strategies[strat_name] = params
            save_strategies(st.session_state.saved_strategies)
            st.session_state.deployed[strat_name] = {
                "started":      datetime.now().strftime("%H:%M:%S"),
                "data":         params,
                "strategy_obj": None,
            }
            st.success("'" + strat_name + "' saved and deployed!")
            st.rerun()

        if btn3.button("Clear Form"):
            st.session_state.legs = []
            st.rerun()


# =============================================================================
# TAB 2 — LIVE DASHBOARD
# =============================================================================
with tabs[1]:
    st.subheader("Live Dashboard")

    auto_refresh_dash = st.checkbox("Auto-refresh every 5 s", value=False, key="dash_autorefresh")
    if auto_refresh_dash:
        time.sleep(5)
        st.rerun()

    deployed = st.session_state.deployed
    if not deployed:
        st.info("No strategies deployed. Go to Strategy Builder and click Save & Deploy.")
    else:
        for sname, dep_info in deployed.items():
            data      = dep_info.get("data", {})
            sym       = data.get("symbol", "?")
            started   = dep_info.get("started", "—")
            strat_obj = dep_info.get("strategy_obj")

            state_str = "—"
            if strat_obj and hasattr(strat_obj, "state"):
                state_str = strat_obj.state

            state_color = {
                "SCANNING": "badge-green",
                "ENTERING": "badge-orange",
                "IN_TRADE": "badge-orange",
                "EXITING":  "badge-orange",
                "EXITED":   "badge-red",
                "IDLE":     "",
            }.get(state_str, "")

            with st.expander(sname + "  |  " + sym + "  |  started " + started, expanded=True):
                top_row = st.columns([1, 3])
                top_row[0].markdown(
                    '<span class="badge ' + state_color + '">' + state_str + '</span>',
                    unsafe_allow_html=True,
                )
                badges = get_active_filter_badges(data)
                if badges:
                    top_row[1].markdown(
                        " ".join('<span class="badge">' + b + '</span>' for b in badges),
                        unsafe_allow_html=True,
                    )
                else:
                    top_row[1].caption("No filters enabled")

                st.divider()

                # VIX panel
                try:
                    from data_store import get_store
                    store = get_store()
                    snap  = store.get_latest_vix()

                    vix_cols = st.columns(5)
                    if snap:
                        vix_cols[0].metric("VIX", str(round(snap.vix, 2)))
                        vix_open = store.get_vix_rth_open()

                        if snap.vix9d > 0:
                            ratio = snap.vix9d / snap.vix
                            vix_cols[1].metric("VIX9D", str(round(snap.vix9d, 2)))
                            vix_cols[2].metric("VIX9D / VIX", str(round(ratio, 4)))
                        else:
                            vix_cols[1].caption("VIX9D — not printed yet")
                            vix_cols[2].caption("Ratio — awaiting VIX9D")

                        if vix_open:
                            id_move_pct = (snap.vix - vix_open) / vix_open * 100
                            id_move_pts = snap.vix - vix_open
                            vix_cols[3].metric("VIX Intraday (%)", str(round(id_move_pct, 2)) + "%")
                            vix_cols[4].metric("VIX Intraday (pts)", str(round(id_move_pts, 2)))
                        else:
                            vix_cols[3].caption("VIX RTH open not locked yet")

                        snaps     = store.get_vix_snaps()
                        pre_snaps = [s for s in snaps if s.ts < "09:25"]
                        if pre_snaps:
                            prev_close = pre_snaps[-1].vix
                            on_pct     = (snap.vix - prev_close) / prev_close * 100
                            on_pts     = snap.vix - prev_close
                            st.markdown(
                                '<div class="vix-metric">VIX Overnight: prev close '
                                + str(round(prev_close, 2)) + " to current "
                                + str(round(snap.vix, 2)) + " | "
                                + str(round(on_pct, 2)) + "% | "
                                + str(round(on_pts, 2)) + " pts</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("VIX — awaiting first data point")
                except Exception as e:
                    st.caption("DataStore not initialised (" + str(e) + ")")

                st.divider()

                # Underlying panel
                try:
                    price    = store.get_latest_close(sym)
                    rth_open = store.get_rth_open(sym)
                    daily    = store.get_daily_closes(sym)

                    price_cols = st.columns(4)
                    if price:
                        price_cols[0].metric(sym + " Last", str(round(price, 2)))
                    else:
                        price_cols[0].caption(sym + " — awaiting bars")

                    if rth_open:
                        price_cols[1].metric("RTH Open", str(round(rth_open, 2)))
                        if price:
                            id_sym_pct = (price - rth_open) / rth_open * 100
                            id_sym_pts = price - rth_open
                            price_cols[2].metric(
                                "Intraday Move",
                                str(round(id_sym_pct, 2)) + "%",
                                delta=str(round(id_sym_pts, 2)) + " pts",
                            )
                    else:
                        price_cols[1].caption("RTH open not locked yet")

                    if daily:
                        prev_close = daily[-1].close
                        price_cols[3].metric("Prev Close", str(round(prev_close, 2)))
                        if rth_open:
                            gap_pct = (rth_open - prev_close) / prev_close * 100
                            st.markdown(
                                '<div class="vix-metric">Gap: prev close '
                                + str(round(prev_close, 2)) + " to RTH open "
                                + str(round(rth_open, 2)) + " | "
                                + str(round(gap_pct, 2)) + "%</div>",
                                unsafe_allow_html=True,
                            )
                except Exception:
                    pass

                st.divider()

                # Open trade panel
                if strat_obj and strat_obj.state == "IN_TRADE":
                    trade_cols = st.columns(4)
                    entry = strat_obj.entry_fill_price
                    trade_cols[0].metric("Entry Fill", str(round(entry, 2)) if entry else "—")
                    if entry:
                        try:
                            current_opt = store.get_latest_close(sym)
                            if current_opt:
                                pnl = strat_obj.risk.pnl_pct(current_opt)
                                trade_cols[1].metric("Unrealised P&L", str(round(pnl * 100, 2)) + "%")
                        except Exception:
                            pass
                    trade_cols[2].metric("Trades Today",
                        str(strat_obj.risk.trades_today) if strat_obj else "—")
                    trade_cols[3].metric("Daily Loss",
                        "$" + str(round(abs(strat_obj.risk.daily_loss), 2)) if strat_obj else "—")

                # Indicators panel
                try:
                    ind = store.get_indicators(sym)
                    if ind:
                        ind_cols = st.columns(5)
                        ind_cols[0].metric("RSI-14", str(round(ind.rsi14, 1)) if ind.rsi14 else "—")
                        for i, (period, val) in enumerate(list(ind.sma.items())[:2]):
                            ind_cols[i + 1].metric("SMA-" + str(period), str(round(val, 2)) if val else "—")
                        for i, (period, val) in enumerate(list(ind.ema.items())[:2]):
                            ind_cols[i + 3].metric("EMA-" + str(period), str(round(val, 2)) if val else "—")
                except Exception:
                    pass


# =============================================================================
# TAB 3 — TRADE LOG
# =============================================================================
with tabs[2]:
    st.subheader("Trade & Strategy Log")

    filter_row = st.columns([1, 1, 1, 1, 2])
    vix_only         = filter_row[0].checkbox("VIX Lines Only",  key="log_vix")
    errors_only      = filter_row[1].checkbox("Errors Only",     key="log_err")
    entries_only     = filter_row[2].checkbox("Entries / Exits", key="log_trade")
    auto_refresh_log = filter_row[3].checkbox("Auto-refresh (5s)", value=False, key="log_autorefresh")
    search_term      = filter_row[4].text_input("Search log text",
        placeholder="e.g. VIX BLOCK, SPY, Filled", key="log_search")

    if auto_refresh_log:
        time.sleep(5)
        st.rerun()

    all_lines = []
    for sname, dep_info in st.session_state.deployed.items():
        strat_obj = dep_info.get("strategy_obj")
        if strat_obj and hasattr(strat_obj, "log"):
            for line in strat_obj.log[-1000:]:
                all_lines.append("[" + sname + "] " + line)

    if not all_lines:
        st.info("No log entries yet. Deploy a strategy and it will log here in real time.")
    else:
        filtered = list(all_lines)

        if vix_only:
            filtered = [
                l for l in filtered
                if any(tag in l for tag in
                       ["[VIX", "VIX9D", "VIX ID", "VIX EXIT",
                        "VIX BLOCK", "vix_on", "vix_id"])
            ]
        if errors_only:
            filtered = [l for l in filtered if "[ERROR]" in l]
        if entries_only:
            filtered = [
                l for l in filtered
                if any(tag in l for tag in
                       ["Entered", "Exit complete", "PROFIT_TARGET",
                        "STOP_LOSS", "TRAILING_STOP", "VIX_EXIT",
                        "TIMED_EXIT", "Signal fired"])
            ]
        if search_term.strip():
            filtered = [l for l in filtered if search_term.lower() in l.lower()]

        st.markdown("Showing **" + str(len(filtered)) + "** of **" + str(len(all_lines)) + "** lines")

        for line in reversed(filtered[-300:]):
            if "[VIX BLOCK]" in line or "[VIX ID]" in line:
                css = "log-block"
            elif "[VIX EXIT]" in line:
                css = "log-exit"
            elif "[ERROR]" in line:
                css = "log-error"
            elif any(t in line for t in ["Entered", "Exit complete", "Signal fired"]):
                css = "log-entry"
            else:
                css = "log-normal"

            st.markdown(
                '<div class="log-line ' + css + '">' + line + '</div>',
                unsafe_allow_html=True,
            )
