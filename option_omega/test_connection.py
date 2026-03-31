# test_paper.py
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
import threading, time

class Test(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
    def nextValidId(self, orderId):
        print(f"Connected to PAPER TWS. Next Order ID: {orderId}")
        self.disconnect()
    def error(self, reqId, code, msg, *args):
        print(f"Error {code}: {msg}")

app = Test()
app.connect("127.0.0.1", 7497, clientId=99)
threading.Thread(target=app.run, daemon=True).start()
time.sleep(5)
