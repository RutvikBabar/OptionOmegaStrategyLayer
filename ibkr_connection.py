from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
import threading, time

class IBApi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

    def nextValidId(self, orderId):
        print(f"✅ Connected! Next Order ID: {orderId}")
        self.reqMarketDataType(4)           # 4 = delayed data (no subscription needed)
        self.request_option_chain()

    def request_option_chain(self):
        contract = Contract()
        contract.symbol   = "SPY"
        contract.secType  = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = "20260320"  # expiry
        contract.strike   = 580.0
        contract.right    = "C"             # Call
        contract.multiplier = "100"
        self.reqMktData(1, contract, "", False, False, [])

    def tickPrice(self, reqId, tickType, price, attrib):
        print(f"Tick | ReqId: {reqId} | Type: {tickType} | Price: {price}")

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(f"Error {errorCode}: {errorString}")

app = IBApi()
app.connect("127.0.0.1", 7497, clientId=1)  # 7497 = paper trading port

thread = threading.Thread(target=app.run, daemon=True)
thread.start()

time.sleep(5)  # let it receive data
app.disconnect()
