import json
import websocket
import threading

class WebsocketsClient(object):
    def __init__(self, ws_uri, exchange_client):
        self._ws_url = ws_uri
        self.exchange_client = exchange_client
        # self._ws_url = 'wss://ws.bitso.com'
        self.ws_client = websocket.WebSocketApp(self._ws_url,
                                                on_message=self._on_message,
                                                on_error=self._on_error,
                                                on_close=self._on_close)

        self.wst = threading.Thread(target=self.connect)
        self.wst.daemon = True
        self.wst.start()
        self._print = False
    def connect(self):
        self.ws_client.on_open = self._on_open
        self.ws_client.run_forever()

    def send(self, message):
        self.ws_client.send(json.dumps(message))

    def close(self):
        self.ws_client.close()

    def _on_close(self, ws):
        pass

    def _on_error(self, ws, error):
        print(error)

    def _on_open(self, ws):
        pass
        # self.ws_client.send(json.dumps({'action': 'subscribe', 'book': 'btc_mxn', 'type': 'orders'}))
    #     for channel in self.channels:
    #         self.ws_client.send(json.dumps({'action': 'subscribe', 'book': self.book, 'type': channel}))
    #     self.listener.on_connect()

    def _on_message(self, ws, m):
        if self._print is False:
            self.exchange_client.websocket_handler(json.loads(m))
        else:
            print(m)
