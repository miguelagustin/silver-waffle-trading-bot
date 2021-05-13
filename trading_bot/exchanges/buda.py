from trading_bot.exceptions import *
from trading_bot import base
from trading_bot.base.exchange import Order
from trading_bot.base.side import ASK, BID
from trading_bot.base.exchange_client import ExchangeClient
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_fixed
import requests
from trading_bot.utilities import truncate
import base64
import hmac
import time
import requests.auth
import simplejson

class BudaHMACAuth(requests.auth.AuthBase):
    """Adjunta la autenticación HMAC de Buda al objeto Request."""

    def __init__(self, api_key: str, secret: str):
        self.api_key = api_key
        self.secret = secret

    def get_nonce(self) -> str:
        # 1. Generar un nonce (timestamp en microsegundos)
        return str(int(time.time() * 1e6))

    def sign(self, r, nonce: str) -> str:
        # 2. Preparar string para firmar
        components = [r.method, r.path_url]
        if r.body:
            encoded_body = base64.b64encode(r.body).decode()
            components.append(encoded_body)
        components.append(nonce)
        msg = ' '.join(components)
        # 3. Obtener la firma
        h = hmac.new(key=self.secret.encode(),
                     msg=msg.encode(),
                     digestmod='sha384')
        signature = h.hexdigest()
        return signature

    def __call__(self, r):
        nonce = self.get_nonce()
        signature = self.sign(r, nonce)
        # 4. Adjuntar API-KEY, nonce y firma al header del request
        r.headers['X-SBTC-APIKEY'] = self.api_key
        r.headers['X-SBTC-NONCE'] = nonce
        r.headers['X-SBTC-SIGNATURE'] = signature
        return r


number_of_attempts = 100


def is_not_local_exception(exception):
    return not isinstance(exception, (not_enough_balance, amount_must_be_greater, stuck_order, currency_doesnt_exist))


class Buda(ExchangeClient):
    def __init__(self, public_key=None, secret_key=None):
        self.name = 'Buda'
        # if not read_only and (public_key is None or secret_key is None):
        #     public_key = input('Enter your public key: ')
        #     secret_key = input('Enter your private key: ')
        self.base_uri = 'https://www.buda.com/api'
        self.api_type = 'REST'
        if public_key and secret_key:
            self.auth = BudaHMACAuth(public_key, secret_key)
        self.timeout = 5
        super().__init__(read_only=True if not (public_key and secret_key) else False)


    @retry(stop=stop_after_attempt(number_of_attempts),wait=wait_fixed(0.2))
    def get_book(self, pair):
        # try:
        response = requests.get(f"{self.base_uri}/v2/markets/{pair.ticker}/order_book", timeout=self.timeout)
        book = response.json()['order_book']
        # except JSONDecodeError:
        #     print(response)

        asks = [{'amount': x[1], 'price': x[0]} for x in book['asks']]
        bids = [{'amount': x[1], 'price': x[0]} for x in book['bids']]
        return {ASK: asks, BID: bids}

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_active_orders(self, pair):
        result = {ASK: [], BID: []}
        try:
            response = requests.get(f"{self.base_uri}/v2/markets/{pair.ticker}/orders", auth=self.auth,
                                    timeout=self.timeout).json()
            orders = response['orders']
        except KeyError:
            print(response)
        for order in orders:
            if order['state'] == 'canceled':
                continue
            side = ASK if order['type'].lower() == 'ask' else BID
            result[side].append(Order(order['limit'][0], side, order['amount'][0], order_id=order['id'], pair=pair))
        return result

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def cancel_order(self, order):
        requests.put(f"{self.base_uri}/v2/orders/{order.order_id}", auth=self.auth, json={'state': 'canceling'},
                     timeout=self.timeout).json()

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def get_balance(self, currency):
        try:
            response = requests.get(f"{self.base_uri}/v2/balances", auth=self.auth, timeout=self.timeout)
            balances = response.json()['balances']
        except KeyError:
            print(response.content)
        try:
            search_result = next(item for item in balances if item["id"].lower() == currency.symbol.lower())
        except StopIteration:
            raise currency_doesnt_exist
        return [search_result['available_amount'][0], search_result['frozen_amount'][0]]

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def create_order(self, pair, amount, side, limit_price=None):
        body = {}
        body['price_type'] = 'LIMIT' if limit_price else 'MARKET'
        body['amount'] = truncate(amount, 5)
        if limit_price:
            body['limit'] = limit_price
        body['type'] = 'Ask' if side is ASK else 'Bid'
        response = requests.post(f"{self.base_uri}/v2/markets/{pair.ticker}/orders", json=body, auth=self.auth,
                                 timeout=self.timeout).json()

    def subscribe(self, pair):
        self._register_pair_and_currencies(pair)
        if self.api_type == 'REST':
            self.__start_threads__(pair)

    def unsubscribe(self, pair):
        pass

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def get_list_of_currencies_and_pairs(self, auto_register=False):
        response = requests.get(f"{self.base_uri}/v2/markets", timeout=self.timeout).json()
        pairs = response['markets']
        list_of_currencies = set([])
        list_of_pairs = []
        for pair in pairs:
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
                                      minimum_step=pair['minimum_order_amount'][0], exchange_client=self)
            list_of_pairs.append(pair)
            list_of_currencies.add(quote_curr)
            list_of_currencies.add(base_curr)
        if auto_register is True:
            for pair in list_of_pairs:
                self._register_pair_and_currencies(pair)
        return list(list_of_currencies), list_of_pairs

    def get_history(self, pair):
        response = requests.get(f"{self.base_uri}/v1/trade/{pair.ticker}/", headers=self.headers,
                                timeout=self.timeout).json()
        print(response)
