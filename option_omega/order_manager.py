"""
order_manager.py
================
Handles limit order fill progression for entry and exit.

Entry behaviour (per OO spec)
------------------------------
  - Start at mid + starting_offset
  - Adjust by price_adjustment every interval_seconds
  - After max_attempts:
      · If retry_minutes > 0  → reset to fresh mid, keep retrying until window
      · If retry_minutes == 0 → convert to market order immediately

Exit behaviour (per OO spec)
-----------------------------
  - Start at mid + starting_offset
  - Adjust by price_adjustment every interval_seconds
  - After max_attempts:
      · use_market_after_attempts=True  → market order
      · use_market_after_attempts=False → reset to current mid at top of next
                                          minute and retry recursively
  - Bid-ask spread guard: checked before each attempt; if spread too wide
    the attempt is skipped (counted against max_attempts for bail-out)
"""

import time
from config import EntryExecution, ExitExecution


class OrderManager:

    def __init__(self, ibkr_client):
        self.ibkr = ibkr_client

    def _get_mid(self, contract) -> float:
        return self.ibkr.get_option_price(contract)

    # ── Entry ─────────────────────────────────────────────────────────────────
    def enter(self, contract, quantity: int,
              cfg: EntryExecution) -> float:
        mid   = self._get_mid(contract)
        price = round(mid + cfg.starting_offset, 2)
        print(f"[Entry] Starting limit @ {price:.2f} "
              f"(mid={mid:.2f}, offset={cfg.starting_offset:+.2f})")

        deadline = (time.time() + cfg.retry_minutes * 60) \
                   if cfg.retry_minutes > 0 else None

        attempt = 0
        while True:
            # Time cap check
            if deadline and time.time() >= deadline:
                print(f"[Entry] {cfg.retry_minutes}m retry window expired — "
                      f"abandoning entry")
                return 0.0

            # Attempt cap check
            if attempt >= cfg.max_attempts:
                if deadline:
                    print(f"[Entry] Max attempts reached — resetting to "
                          f"current mid within {cfg.retry_minutes}m window")
                    attempt = 0
                    mid     = self._get_mid(contract)
                    price   = round(mid + cfg.starting_offset, 2)
                    time.sleep(cfg.interval_seconds)
                    continue
                else:
                    print("[Entry] Max attempts reached — submitting market order")
                    return self.ibkr.place_market_order(contract, "BUY", quantity)

            attempt += 1
            fill     = self.ibkr.place_limit_order(contract, "BUY",
                                                    quantity, price)
            if fill:
                print(f"[Entry] Filled @ {fill:.2f} on attempt {attempt}")
                return fill

            price = round(price + cfg.price_adjustment, 2)
            print(f"[Entry] Attempt {attempt} — no fill, "
                  f"adjusting to {price:.2f}")
            time.sleep(cfg.interval_seconds)

    # ── Exit ──────────────────────────────────────────────────────────────────
    def exit(self, contract, quantity: int,
             cfg: ExitExecution, bid_ask_filter=None) -> float:
        mid   = self._get_mid(contract)
        price = round(mid + cfg.starting_offset, 2)
        print(f"[Exit] Starting limit @ {price:.2f} "
              f"(mid={mid:.2f}, offset={cfg.starting_offset:+.2f})")

        for attempt in range(1, cfg.max_attempts + 1):
            # Bid-ask spread check before each attempt
            if bid_ask_filter and bid_ask_filter.enabled:
                if not self._spread_acceptable(contract, bid_ask_filter):
                    if attempt >= bid_ask_filter.max_attempts:
                        print("[Exit] Bid-ask max attempts exceeded — "
                              "forcing exit regardless of spread")
                    else:
                        print(f"[Exit] Spread too wide — "
                              f"skipping attempt {attempt}")
                        time.sleep(cfg.interval_seconds)
                        continue

            fill = self.ibkr.place_limit_order(contract, "SELL",
                                               quantity, price)
            if fill:
                print(f"[Exit] Filled @ {fill:.2f} on attempt {attempt}")
                return fill

            price = round(price + cfg.price_adjustment, 2)
            print(f"[Exit] Attempt {attempt} — no fill, "
                  f"adjusting to {price:.2f}")
            time.sleep(cfg.interval_seconds)

        # Post-loop: market order or reset
        if cfg.use_market_after_attempts:
            print("[Exit] Switching to market order after all attempts")
            return self.ibkr.place_market_order(contract, "SELL", quantity)

        print("[Exit] Resetting to current mid at top of next minute — retrying")
        return self.exit(contract, quantity, cfg, bid_ask_filter)

    # ── Bid-ask helper ────────────────────────────────────────────────────────
    def _spread_acceptable(self, contract, baf) -> bool:
        try:
            bid  = self.ibkr.get_bid(contract)
            ask  = self.ibkr.get_ask(contract)
            if baf.mode == "percentage":
                mid    = (bid + ask) / 2
                spread = (ask - bid) / mid if mid > 0 else 999
            else:
                spread = ask - bid
            return spread <= baf.max_spread_width
        except Exception:
            return True   # fail open — never block an exit due to data error