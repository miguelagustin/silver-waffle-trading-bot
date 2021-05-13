from trading_bot.exceptions import *
from trading_bot import base
from trading_bot.base.exchange import Order
from trading_bot.base.side import ASK, BID
from trading_bot.base.exchange_client import ExchangeClient, WebsocketsClient
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed
import requests
from time import sleep
from trading_bot.utilities import truncate
import base64
import hmac
import time
import requests.auth

number_of_attempts = 10


def is_not_local_exception(exception):
    return not isinstance(exception, (not_enough_balance, amount_must_be_greater, stuck_order, currency_doesnt_exist))


class Coinbase(ExchangeClient):
    def __init__(self, public_key=None, secret_key=None):
        self.name = 'Coinbase'
        # if not read_only and (public_key is None or secret_key is None):
        #     public_key = input('Enter your public key: ')
        #     secret_key = input('Enter your private key: ')
        self.base_uri = 'https://api.pro.coinbase.com'
        self.timeout = 5

        super().__init__(read_only=True if not (public_key and secret_key) else False,
                         websockets_client=WebsocketsClient('wss://ws-feed.pro.coinbase.com'))

    def websocket_handler(self, message):
        if message['type'] == 'orders' and 'payload' in message:
            book = {ASK: None, BID: None}
            for side in [ASK, BID]:
                _side = 'bids' if side is BID else 'asks'
                book[side] = [{'amount': order['a'], 'price': order['r']} for order in message['payload'][_side]]
            self.pairs_by_ticker[message['book']].orderbook.update(book)

    @retry(stop=stop_after_attempt(number_of_attempts), wait=wait_fixed(0.2))
    def get_book(self, pair):
        # try:<product-id>/book
        response = requests.get(f"{self.base_uri}/products/{pair.ticker}/book?level=2", timeout=self.timeout)
        try:
            book = response.json()
        except KeyError:
            print(response.content)
        # except JSONDecodeError:
        #     print(response)

        asks = [{'amount': x[1], 'price': x[0]} for x in book['asks']]
        bids = [{'amount': x[1], 'price': x[0]} for x in book['bids']]
        return {ASK: asks, BID: bids}

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_active_orders(self, pair):
        pass

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def cancel_order(self, order):
        pass

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def get_balance(self, currency):
        pass

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def create_order(self, pair, amount, side, limit_price=None):
        pass

    def subscribe(self, pair):
        self._register_pair_and_currencies(pair)
        if self.socket_functionality[pair]['book'] is False:
            self.__start_threads__(pair)
        else:
            if self.websockets_client.is_closed:
                self.websockets_client.connect()
                sleep(2)
            self.websockets_client.send({'action': 'subscribe', 'book': pair.ticker, 'type': 'orders'})

    def unsubscribe(self, pair):
        # It has to be sent twice for it to work, no idea why
        if self.websockets_client.is_closed is not True:
            self.websockets_client.send({'action': 'unsubscribe', 'book': pair.ticker, 'type': 'orders'})
            self.websockets_client.send({'action': 'unsubscribe', 'book': pair.ticker, 'type': 'orders'})

    def get_list_of_currencies_and_pairs(self):
        response = requests.get(f"{self.base_uri}/products/", timeout=self.timeout)

        try:
            pairs_response = response.json()
        except KeyError:
            print(response.content)
        list_of_currencies = set([])
        list_of_pairs = []
        for pair in pairs_response:
            try:
                base_curr = quote_curr = None
                for curr in list_of_currencies:
                    if pair['base_currency'] == curr.symbol:
                        base_curr = curr
                    if pair['quote_currency'] == curr.symbol:
                        quote_curr = curr
                if not base_curr:
                    base_curr = base.exchange.Currency(name=pair['base_currency'], symbol=pair['base_currency'],
                                                       exchange_client=self)
                if not quote_curr:
                    quote_curr = base.exchange.Currency(name=pair['quote_currency'], symbol=pair['quote_currency'],
                                                        exchange_client=self)
            except currency_doesnt_exist:
                continue
            pair = base.exchange.Pair(ticker=pair['id'], quote=quote_curr, base=base_curr,
                                      minimum_step=pair['quote_increment'], exchange_client=self)
            list_of_pairs.append(pair)
            list_of_currencies.add(quote_curr)
            list_of_currencies.add(base_curr)
        return list(list_of_currencies), list_of_pairs

    def get_history(self, pair):
        pass
