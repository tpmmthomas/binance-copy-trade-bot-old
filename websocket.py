from time import sleep
import binance
btc_price = {'error':False}
def btc_trade_history(msg):
    ''' define how to process incoming WebSocket messages '''
    with open("data.log","ab") as f:
        f.write(msg['c'])

bsm = binance.ThreadedWebsocketManager()
bsm.start()
bsm.start_symbol_ticker_socket(callback=btc_trade_history,symbol='BTCUSDT')
