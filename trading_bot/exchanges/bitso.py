from trading_bot.exceptions import *
from trading_bot import base
from trading_bot.base.exchange import Order
from trading_bot.base.side import ASK, BID
from trading_bot.base.exchange_client import ExchangeClient
from tenacity import retry, retry_if_exception, stop_after_attempt
import requests
from trading_bot.utilities import truncate
import base64
import hmac
import time
import requests.auth


number_of_attempts = 10


def is_not_local_exception(exception):
    return not isinstance(exception, (not_enough_balance, amount_must_be_greater, stuck_order, currency_doesnt_exist))


class Bitso(ExchangeClient):
    def __init__(self, public_key=None, secret_key=None):
        super().__init__(read_only=True if not (public_key and secret_key) else False)
        self.name = 'Bitso'
        # if not read_only and (public_key is None or secret_key is None):
        #     public_key = input('Enter your public key: ')
        #     secret_key = input('Enter your private key: ')
        self.base_uri = 'https://api.bitso.com/'
        self.api_type = 'REST'
        self.timeout = 5

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_book(self, pair):
        # try:
        response = requests.get(f"{self.base_uri}/v3/order_book/?book={pair.ticker}", timeout=self.timeout)
        try:
            book = response.json()['payload']
        except KeyError:
            print(response)
        # except JSONDecodeError:
        #     print(response)

        asks = [{'amount': x['amount'], 'price': x['price']} for x in book['asks']]
        bids = [{'amount': x['amount'], 'price': x['price']} for x in book['bids']]
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
        if self.api_type == 'REST':
            self.__start_threads__(pair)

    def unsubscribe(self, pair):
        pass

    def get_list_of_currencies_and_pairs(self, auto_register=False):
        response = requests.get(f"{self.base_uri}/v3/available_books/", timeout=self.timeout)

        try:
            pairs_response = response.json()['payload']
        except KeyError:
            print(response.content)
        list_of_currencies = set([])
        list_of_pairs = []
        for pair in pairs_response:
            from pprint import pprint

            currencies_symbols = pair['book'].split('_')
            pprint(currencies_symbols)
            try:
                base_curr = quote_curr = None
                for curr in list_of_currencies:
                    if currencies_symbols[0] == curr.symbol:
                        base_curr = curr
                    if currencies_symbols[1] == curr.symbol:
                        quote_curr = curr
                if not base_curr:
                    base_curr = base.exchange.Currency(name=currencies_symbols[0], symbol=currencies_symbols[0],
                                              exchange_client=self)
                if not quote_curr:
                    quote_curr = base.exchange.Currency(name=currencies_symbols[1], symbol=currencies_symbols[1],
                                               exchange_client=self)
            except currency_doesnt_exist:
                continue
            pair = base.exchange.Pair(ticker=pair['book'], quote=quote_curr, base=base_curr,
                             minimum_step=pair['minimum_value'], exchange_client=self)
            list_of_pairs.append(pair)
            list_of_currencies.add(quote_curr)
            list_of_currencies.add(base_curr)
        if auto_register is True:
            for pair in list_of_pairs:
                self._register_pair_and_currencies(pair)
        return list(list_of_currencies), list_of_pairs

    def get_history(self, pair):
        pass