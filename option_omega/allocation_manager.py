"""
allocation_manager.py
=====================
Calculates the number of contracts to trade based on
allocation type: percentage of NLV, fixed dollar value, or fixed quantity.
"""


class AllocationManager:

    def __init__(self, ibkr_client, config):
        self.ibkr  = ibkr_client
        self.funds = config.funds

    def get_quantity(self, option_price: float) -> int:
        """
        Returns the number of contracts to trade.
        option_price : current option mid price per share (not per contract).
        Cost per contract = option_price * 100.
        """
        alloc_type = self.funds.allocation_type

        if alloc_type == "fixed_quantity":
            return max(1, int(self.funds.max_contracts))

        if alloc_type == "fixed_value":
            cost_per_contract = option_price * 100
            if cost_per_contract <= 0:
                return 1
            qty = int(self.funds.max_fixed_value // cost_per_contract)
            return max(1, qty)

        if alloc_type == "percentage":
            try:
                nlv = self.ibkr.get_account_nlv()
            except Exception:
                return 1
            budget            = nlv * (self.funds.percentage / 100.0)
            cost_per_contract = option_price * 100
            if cost_per_contract <= 0:
                return 1
            qty = int(budget // cost_per_contract)
            return max(1, qty)

        return 1