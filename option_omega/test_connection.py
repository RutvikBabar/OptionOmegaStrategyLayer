# test_connection.py
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

class Test(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
    def nextValidId(self, orderId):
        print(f"✅ Connected! Next Order ID: {orderId}")
        self.disconnect()

app = Test()
app.connect("127.0.0.1", 7497, clientId=99)
app.run()