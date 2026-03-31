# Market data for an options contract
app.reqMktData(reqId, contract, "", False, False, [])

# Place an options order
from ibapi.order import Order
order = Order()
order.action    = "BUY"
order.orderType = "LMT"
order.totalQuantity = 1
order.lmtPrice  = 2.50
app.placeOrder(app.nextOrderId, contract, order)

# Options-specific: request Greeks (delta, gamma, theta, vega)
app.reqMktData(reqId, contract, "100", False, False, [])
# tickType 10-13 = bid/ask implied vol + Greeks via tickOptionComputation()
