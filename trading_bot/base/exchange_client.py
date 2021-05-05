import threading
from forex_python.converter import CurrencyCodes
from abc import ABC, abstractmethod
from time import sleep, time
import requests
import sys
from .constants import STABLECOIN_SYMBOLS
from .side import ASK, BID

import json
import websocket
import threading


class ExchangeClient(ABC):
    def __init__(self, is_rate_limited=False, read_only=False, websockets_client=None):
        self.websockets_client = websockets_client
        self.read_only = read_only
        self._update_delay = 1
        self._update_balance_sleep_time = 7
        self.pairs = set()
        self.pairs_by_ticker = {}
        self.pairs_to_always_update = set()
        self.currencies_by_symbol = {}
        self.currencies = set()
        self.is_rate_limited = is_rate_limited
        self._rate_limits_timestamps = {}
        self.cooldown = 2
        self.threads = {}
        self.update_book_if_balance_is_empty = True

    @abstractmethod
    def get_book(self, book):
        pass

    @abstractmethod
    def get_balance(self):
        pass

    @abstractmethod
    def get_active_orders(self, pair):
        pass

    @abstractmethod
    def cancel_order(self, order):
        pass

    @abstractmethod
    def create_order(self):
        pass

    @abstractmethod
    def subscribe(self, pair):
        pass

    @abstractmethod
    def unsubscribe(self, pair):
        pass

    @abstractmethod
    def get_list_of_currencies_and_pairs(self):
        pass

    def get_pair_by_ticker(self, ticker):
        for pair in self.pairs:
            if pair.ticker.lower() == ticker.lower():
                return pair

    def _register_pair_and_currencies(self, pair):
        self.pairs.add(pair)
        self.currencies.add(pair.quote)
        self.currencies.add(pair.base)
        self.pairs_by_ticker.update({pair.ticker: pair})
        self.currencies_by_symbol.update({pair.quote.symbol: pair.quote, pair.base.symbol: pair.base})

    def _is_symbol_a_cryptocurrency(self, symbol: str):
        return True if CurrencyCodes().get_symbol(symbol) is None else False

    def __start_threads__(self, pair):
        def launch_thread(thread, pair_or_currency):
            thread = threading.Thread(target=thread, args=[pair_or_currency])
            thread.daemon = True
            if pair_or_currency not in self.threads:
                self.threads[pair_or_currency] = []
            self.threads[pair_or_currency].append(thread)
            thread.start()

        assert pair in self.pairs
        if not (pair in self.threads and self.threads[pair]):
            launch_thread(self.__update_book_daemon__, pair)
            for currency in [pair.quote, pair.base]:
                if not (currency in self.threads and self.threads[currency]):
                    launch_thread(self.__update_global_price_daemon__, currency)
                    if self.read_only is False:
                        launch_thread(self.__update_balance_daemon__, currency)

    def __update_book_daemon__(self, pair):
        def exit_thread():
            self.threads[pair] = None
            sys.exit()  # exit from the current thread

        while True:
            if not self.update_book_if_balance_is_empty:
                if pair.status[BID] and not pair.status[ASK] and pair.quote.balance_is_empty():
                    sleep(5)
                    continue
                if pair.status[ASK] and not pair.status[BID] and pair.base.balance_is_empty():
                    sleep(5)
                    continue
                if pair.base.balance_is_empty() and pair.quote.balance_is_empty():
                    sleep(5)
                    continue
            if pair or pair in self.pairs_to_always_update:
                pair.orderbook.update(self.get_book(pair))
                sleep(self._update_delay)
            else:
                sleep(5)

    def __update_balance_daemon__(self, currency):
        while True:
            if currency.has_an_active_pair():
                currency.update_balance()
            sleep(self._update_balance_sleep_time)

    def __update_global_price_daemon__(self, currency):
        while True:
            if currency.symbol in STABLECOIN_SYMBOLS:
                currency.global_price = 1
                sys.exit()  # close the daemon
            try:
                currency.update_global_price()
                sleep(120)
            except (requests.exceptions.HTTPError, UnboundLocalError):
                return

    def __str__(self):
        return self.name

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