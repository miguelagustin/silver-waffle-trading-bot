# from abc import ABC, abstractmethod
from time import sleep, time
import requests
import sys
from silver_waffle.base.side import ASK, BID
from silver_waffle.base.exchange import Order, Currency, Pair
from random import randint
import json
import websocket
import ccxt
import threading
from tenacity import RetryError, retry, stop_after_attempt
import importlib

number_of_attempts = 1

class ExchangeClient():
    all_currencies = []

    def __init__(self, exchange: str, websockets_client=None,
                 socket_settings={'book': True, 'orders': True, 'transactions': True},
                 ccxt_client=None, whitelist=None, creds=None):
        try:
            self.ccxt_client = getattr(ccxt, ccxt_client)()
        except AttributeError:
            try:
                module = importlib.import_module(f'silver_waffle.exchanges.{exchange.lower()}')
                return getattr(module, exchange.lower().capitalize())()
            except (ModuleNotFoundError, AttributeError):
                raise ValueError('Exchange not found')
        self.websockets_client = websockets_client
        if creds is None:
            self.read_only = True
        else:
            self.read_only = False
        self._update_book_sleep_time = 1
        self._update_balance_sleep_time = 7
        self.pairs = set()
        self.pairs_by_ticker = {}
        self.pairs_to_always_update = set()
        self.currencies_by_symbol = {}
        self.currencies = set()
        self._rate_limits_timestamps = {}
        self.cooldown = 2
        self.threads = {}
        self.update_book_if_balance_is_empty = True

        self.socket_functionality = {}

        currencies, pairs = self.get_list_of_currencies_and_pairs(whitelist=whitelist)

        for pair in pairs:
            self._register_pair_and_currencies(pair, socket_settings=socket_settings)
            if self.read_only is False:
                for currency in [pair.base, pair.quote]:
                    if not (currency in self.threads and self.threads[currency]):
                        self._launch_thread(self.__update_balance_daemon__, currency)
        self.all_currencies += currencies
        for currency in currencies:
            currency_count = 0
            for all_currency in self.all_currencies:
                if currency.symbol.lower() == all_currency.symbol.lower():
                    currency_count += 1

            if currency_count == 1:
                self._launch_thread(self.__update_global_price_daemon__, currency)

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_book(self, pair):
        """Returns a dictionary containing the buy and sell orders.

        return format: {ASK: list_of_asks, BID: list_of_bids}"""
        book = self.ccxt_client.fetch_order_book(pair.ticker)
        asks = [{'amount': x[1], 'price': x[0]} for x in book['asks']]
        bids = [{'amount': x[1], 'price': x[0]} for x in book['bids']]

        return {ASK: asks, BID: bids}

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_balance(self, currency):
        """Returns the available and locked balance of a currency, in that order"""
        balances = self.ccxt_client.fetch_balance()
        try:
            return balances[currency.symbol]['free'], balances[currency.symbol]['used']
        except KeyError:
            return 0, 0

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_active_orders(self, pair):
        orders = self.ccxt_client.fetch_open_orders(symbol=pair.ticker)
        result = {ASK: [], BID: []}
        for order in orders:
            side = ASK if order['side'] == 'sell' else BID
            result[side].append(Order(order['price'], side, order['amount'], order_id=order['id'], pair=pair))
        return result

    @retry(stop=stop_after_attempt(number_of_attempts))
    def cancel_order(self, order):
        try:
            self.ccxt_client.cancel_order(order.order_id, order.pair.ticker)
        except ccxt.base.errors.ArgumentsRequired:
            print(order.pair.ticker)

    def create_order(self, pair, amount, side, limit_price=None):
        if limit_price is None:
            if side is ASK:
                self.ccxt_client.create_market_sell_order(pair.ticker, amount)
            elif side is BID:
                self.ccxt_client.create_market_buy_order(pair.ticker, amount)
        else:
            if side is ASK:
                order = self.ccxt_client.create_limit_sell_order(pair.ticker, amount, limit_price)
            elif side is BID:
                order = self.ccxt_client.create_limit_buy_order(pair.ticker, amount, limit_price)
            return Order(limit_price, side, amount, pair=pair, order_id=order['id'])

    def subscribe(self, pair):
        self._register_pair_and_currencies(pair)
        self.__start_threads__(pair)

    def unsubscribe(self, pair):
        pass

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_list_of_currencies_and_pairs(self, whitelist=None):
        markets = self.ccxt_client.fetch_markets()
        list_of_currencies = set([])
        list_of_pairs = []
        for pair in markets:
            if pair['active'] is False:
                continue
            try:
                quote_symbol = pair['info']['quoteAsset']
                base_symbol = pair['info']['baseAsset'].replace(quote_symbol, '')
            except KeyError:
                quote_symbol = pair['info']['quote']
                base_symbol = pair['info']['base'].replace(quote_symbol, '')
            base_curr = quote_curr = None
            ticker = pair['symbol']

            #CCXT is inconsistent across exchanges so we have to do this

            for dict_index in ['tickSize', 'price_tick']:
                try:
                    minimum_step = pair['info'][dict_index]
                    break
                except KeyError:
                    try:
                        minimum_step = pair['info']['filters'][0][dict_index]
                        break
                    except KeyError:
                        continue

            if whitelist is not None and ticker not in whitelist:
                continue
            for curr in list_of_currencies:
                if base_symbol == curr.symbol:
                    base_curr = curr
                if quote_symbol == curr.symbol:
                    quote_curr = curr
            if not base_curr:
                base_curr = Currency(name=base_symbol, symbol=base_symbol,
                                     exchange_client=self)
            if not quote_curr:
                quote_curr = Currency(name=quote_symbol, symbol=quote_symbol,
                                      exchange_client=self)
            pair = Pair(ticker=ticker, quote=quote_curr, base=base_curr,
                        minimum_step=minimum_step, exchange_client=self)
            list_of_pairs.append(pair)
            list_of_currencies.add(quote_curr)
            list_of_currencies.add(base_curr)
        return list(list_of_currencies), list_of_pairs

    def get_pair_by_ticker(self, ticker):
        for pair in self.pairs:
            if pair.ticker.lower() == ticker.lower():
                return pair

    def _register_pair_and_currencies(self, pair, socket_settings=None):
        self.pairs.add(pair)
        self.currencies.add(pair.quote)
        self.currencies.add(pair.base)
        self.pairs_by_ticker.update({pair.ticker: pair})
        self.currencies_by_symbol.update({pair.quote.symbol: pair.quote, pair.base.symbol: pair.base})
        if socket_settings:
            self.socket_functionality[pair] = socket_settings

    def _launch_thread(self, thread, pair_or_currency):
        thread = threading.Thread(target=thread, args=[pair_or_currency])
        thread.daemon = True
        if pair_or_currency not in self.threads:
            self.threads[pair_or_currency] = []
        self.threads[pair_or_currency].append(thread)
        thread.start()

    def __start_threads__(self, pair):
        assert pair in self.pairs
        if not (pair in self.threads and self.threads[pair]):
            self._launch_thread(self.__update_book_daemon__, pair)
            # for currency in [pair.quote, pair.base]:
            #     if not (currency in self.threads and self.threads[currency]):
            #

    def __update_book_daemon__(self, pair):
        def exit_thread():
            self.threads[pair] = None
            sys.exit()  # exit from the current thread

        sleep(randint(0, self._update_book_sleep_time))
        while True:
            while self.socket_functionality[pair]['book'] is True and self.websockets_client is not None:
                sleep(self._update_book_sleep_time)
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
                sleep(self._update_book_sleep_time)
            else:
                sleep(5)

    def __update_balance_daemon__(self, currency):
        sleep(randint(0, self._update_balance_sleep_time))
        while True:
            if currency.has_an_active_pair():
                currency.update_balance()
            sleep(self._update_balance_sleep_time)

    def __update_global_price_daemon__(self, currency):
        sleep(randint(20, 80))
        while True:
            currencies_to_update = []
            for all_currency in self.all_currencies:
                if currency.symbol.lower() == all_currency.symbol.lower():
                    currencies_to_update.append(all_currency)
            try:
                price = currency.get_global_price()
            except (requests.exceptions.HTTPError, UnboundLocalError):
                continue
            except Exception:
                sys.exit()
                # log this
            for currency in currencies_to_update:
                currency.global_price = price
            sleep(120)

    def __str__(self):
        return self.name


class WebsocketsClient(object):
    def __init__(self, ws_uri, exchange_client):
        self._ws_url = ws_uri
        self.exchange_client = exchange_client
        self.ws_client = websocket.WebSocketApp(self._ws_url,
                                                on_message=self._on_message,
                                                on_error=self._on_error,
                                                on_close=self._on_close)

        self._print = False
        self.is_closed = True

    def connect(self):
        self.wst = threading.Thread(target=self._connect)
        self.wst.daemon = True
        self.wst.start()

    def _connect(self):
        self.ws_client.on_open = self._on_open
        self.ws_client.run_forever()

    def send(self, message):
        self.ws_client.send(json.dumps(message))

    def close(self):
        self.ws_client.close()

    def _on_close(self, ws):
        self.is_closed = True

    def _on_error(self, ws, error):
        print(error)

    def _on_open(self, ws):
        self.is_closed = False
        # self.ws_client.send(json.dumps({'action': 'subscribe', 'book': 'btc_mxn', 'type': 'orders'}))

    #     for channel in self.channels:
    #         self.ws_client.send(json.dumps({'action': 'subscribe', 'book': self.book, 'type': channel}))
    #     self.listener.on_connect()

    def _on_message(self, ws, m):
        if self._print is False:
            self.exchange_client.websocket_handler(json.loads(m))
        else:
            print(m)
