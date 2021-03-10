from pymitter import EventEmitter
import threading
from forex_python.converter import CurrencyCodes
from abc import ABC, abstractmethod
from time import sleep, time
import requests
import sys
from .exchange import Cryptocurrency
from money import Money
import cryptocompare
import ui
from .side import ASK, BID
from trading_bot.utilities import truncate

class ExchangeClient(ABC):
    def __init__(self, is_rate_limited=False):
        self._update_delay = 1
        self._update_balance_sleep_time = 7
        self.pairs = set({})
        self.pairs_by_ticker = {}
        self.currencies_by_symbol = {}
        self.currencies = set({})
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

    def _register_pair_and_currencies(self, pair):
        self.pairs.add(pair)
        self.currencies.add(pair.quote)
        self.currencies.add(pair.base)
        self.pairs_by_ticker.update({pair.ticker: pair})
        self.currencies_by_symbol.update({pair.quote.symbol: pair.quote, pair.base.symbol: pair.base})

    def _is_symbol_a_cryptocurrency(self, symbol: str):
        return True if CurrencyCodes().get_symbol(symbol) is None else False

    def __start_threads__(self, pair):
        def launch_thread(thread, arg):
            thread = threading.Thread(target=thread, args=[arg])
            thread.daemon = True
            self.threads[arg] = thread
            thread.start()

        assert pair in self.pairs
        if not (pair in self.threads and self.threads[pair]):
            launch_thread(self.__update_book_daemon__, pair)
            for currency in [pair.quote, pair.base]:
                if not (currency in self.threads and self.threads[currency]):
                    launch_thread(self.__update_balance_daemon__, currency)
                if isinstance(currency, Cryptocurrency):
                    launch_thread(self.__update_international_price_daemon__, currency)

    def __update_book_daemon__(self, pair):
        def exit_thread():
            self.threads[pair] = None
            sys.exit()  # exit from the current thread

        while True:
            if not self.update_book_if_balance_is_empty:
                if pair.status[BID] and not pair.status[ASK] and pair.base.balance_is_empty():
                    sleep(5)
                    continue
                if pair.status[ASK] and not pair.status[BID] and pair.quote.balance_is_empty():
                    sleep(5)
                    continue
                if pair.base.balance_is_empty() and pair.quote.balance_is_empty():
                    sleep(5)
                    continue
            if pair:
                pair.orderbook.update(self.get_book(pair))
                sleep(self._update_delay)
            else:
                exit_thread()

    def __update_balance_daemon__(self, currency):
        while True:
            if currency.has_an_active_pair():
                currency.update_balance()
            sleep(self._update_balance_sleep_time)

    def __update_international_price_daemon__(self, currency):
        while True:
            try:
                currency.update_international_price()
                sleep(45)
            except (requests.exceptions.HTTPError, UnboundLocalError):
                return

    def __str__(self):
        return self.name