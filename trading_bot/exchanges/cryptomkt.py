from exceptions import *
from base.exchange import Order, ee
from base.side import ASK, BID
from base.exchange_client import ExchangeClient
from trading_bot.base.exchange import Pair, Currency
from tenacity import retry, retry_if_exception, stop_after_attempt
from utilities import truncate
from decimal import Decimal
from cryptomarket.exchange.client import Client as cryptomkt
from cryptomarket.exchange.error import InvalidRequestError, AuthenticationError, RateLimitExceededError
import requests


number_of_attempts = 15


def is_not_local_exception(exception):
    return not isinstance(exception, (not_enough_balance, amount_must_be_greater, stuck_order))


class Cryptomkt(ExchangeClient):

    def __init__(self, public_key=None, secret_key=None):
        self.name = 'Cryptomarket'
        super().__init__(read_only=True if not (public_key and secret_key) else False)
        if public_key and secret_key:
            self._base_client = cryptomkt(public_key, secret_key)
            self.socket = self._base_client.get_socket()
            self.socket.logger.disabled = True
            self.socket.on('open-book', self._handle_socket_orderbook)
            self.socket.on('balance', self._handle_socket_balance)
        self.base_uri = "https://api.cryptomkt.com/"
        self.timeout = 5

    def _handle_socket_orderbook(self, data):
        for ticker, order_data in data.items():
            parsed_data = {ASK: order_data['sell'], BID: order_data['buy']}
            self.pairs_by_ticker[ticker].orderbook.update(parsed_data)

    def _handle_socket_balance(self, data):
        # pprint(data)
        for symbol, balance_data in data.items():
            for currency in self.currencies:
                if currency.symbol.lower() == symbol.lower():
                    # print(balance_data)
                    currency._set_balance([balance_data['available'], str(
                        Decimal(balance_data['countable']) - Decimal(balance_data['available']))])
        ee.emit("updated_balance")

    def subscribe(self, pair):
        self._register_pair_and_currencies(pair)

        if self.read_only is True:
            self.__start_threads__(pair)
        else:
            self.socket.subscribe(pair.ticker)

    def unsubscribe(self, pair):
        self.socket.unsubscribe(pair.ticker)
        pass

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_book(self, pair):
        response_bid = requests.get(f"{self.base_uri}/v1/book?market={pair.ticker}&type=buy&limit=30", timeout=self.timeout)
        response_ask = requests.get(f"{self.base_uri}/v1/book?market={pair.ticker}&type=sell&limit=30",
                                    timeout=self.timeout)
        try:
            book_bid = response_bid.json()['data']
            book_ask = response_ask.json()['data']
        except KeyError:
            print(response_bid.content, response_ask.content)

        asks = [{'amount': x['amount'], 'price': x['price']} for x in book_ask]
        bids = [{'amount': x['amount'], 'price': x['price']} for x in book_bid]
        return {ASK: asks, BID: bids}

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_active_orders(self, pair):
        result = {ASK: [], BID: []}
        orders = self._base_client.get_active_orders(market=pair.ticker)['data']
        for order in orders:
            try:
                side = ASK if order['side'].lower() == 'sell' else BID
                result[side].append(
                    Order(order['price'], side, order['amount']['original'], order_id=order['id'], pair=pair))
            except (KeyError, AttributeError):
                print(order)
        return result

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def cancel_order(self, order: Order):
        try:
            order = self._base_client.cancel_order(id=order.order_id)
            assert order['status'] == 'cancelled'
        except InvalidRequestError:
            return

    @retry(stop=stop_after_attempt(number_of_attempts))
    def get_balance(self, currency):
        balance = self._base_client.get_balance()['data']
        search_result = next(item for item in balance if item["wallet"].lower() == currency.symbol.lower())
        return [truncate(Decimal(search_result['available']), 3),
                truncate(float(Decimal(search_result['balance']) - Decimal(search_result['available'])), 3)]

    @retry(retry=retry_if_exception(is_not_local_exception), stop=stop_after_attempt(number_of_attempts))
    def create_order(self, pair, amount, side, limit_price=None):
        try:
            if limit_price:
                order = self._base_client.create_order(market=pair.ticker, type="limit", amount=truncate(amount, 4),
                                          price=limit_price, side="sell" if side is ASK else "buy")
                return Order(order['price'], side, order['amount']['original'], order_id=order['id'], pair=pair)
            else:
                self._base_client.create_order(market=pair.ticker, type="market", amount=truncate(amount, 4),
                                  side="sell" if side is ASK else "buy")
        except InvalidRequestError as e:
            if e.message == 'not_enough_balance':
                print(f"not enough balance: {amount}")
                raise not_enough_balance
            if e.message == 'invalid_request':
                raise server_error

    def get_list_of_currencies_and_pairs(self):
        # Since cryptomarket doesn't have the endpoints to auto create the pairs, this has to be done manually.
        ars = Currency(name='Argentinian Peso', symbol='ars', exchange_client=self)
        brl = Currency(name='Brazilian Real', symbol='brl', exchange_client=self)
        clp = Currency(name='Chilean Peso', symbol='clp', exchange_client=self)

        eth = Currency(name='Ethereum', symbol='eth', exchange_client=self)
        xlm = Currency(name='Stellar', symbol='xlm', exchange_client=self)
        eos = Currency(name='EOS', symbol='eos', exchange_client=self)
        btc = Currency(name='Bitcoin', symbol='btc', exchange_client=self)

        ethars = Pair(exchange_client=self, ticker='ETHARS', base=eth, quote=ars, minimum_step=2)
        xlmars = Pair(exchange_client=self, ticker='XLMARS', base=xlm, quote=ars, minimum_step=0.005)
        eosars = Pair(exchange_client=self, ticker='EOSARS', base=eos, quote=ars, minimum_step=0.05)
        btcars = Pair(exchange_client=self, ticker='BTCARS', base=btc, quote=ars, minimum_step=20)

        ethbrl = Pair(exchange_client=self, ticker='ETHARS', base=eth, quote=brl, minimum_step=2)
        xlmbrl = Pair(exchange_client=self, ticker='XLMARS', base=xlm, quote=brl, minimum_step=0.005)
        eosbrl = Pair(exchange_client=self, ticker='EOSARS', base=eos, quote=brl, minimum_step=0.05)
        btcbrl = Pair(exchange_client=self, ticker='BTCARS', base=btc, quote=brl, minimum_step=20)

        ethclp = Pair(exchange_client=self, ticker='ETHARS', base=eth, quote=clp, minimum_step=2)
        xlmclp = Pair(exchange_client=self, ticker='XLMARS', base=xlm, quote=clp, minimum_step=0.005)
        eosclp = Pair(exchange_client=self, ticker='EOSARS', base=eos, quote=clp, minimum_step=0.05)
        btcclp = Pair(exchange_client=self, ticker='BTCARS', base=btc, quote=clp, minimum_step=20)

        list_of_pairs = [ethars, xlmars, eosars, btcars, ethbrl, xlmbrl, eosbrl, btcbrl, ethclp, xlmclp, eosclp, btcclp]
        list_of_currencies = [ars, brl, clp, eth, xlm, eos, btc]

        return list_of_currencies, list_of_pairs


    def get_history(self, pair):
        pass