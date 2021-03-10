from exceptions import *
from base.exchange import Order, ee
from base.side import ASK, BID
from base.exchange_client import ExchangeClient
from tenacity import retry, retry_if_exception, stop_after_attempt
from utilities import truncate
from decimal import Decimal
from cryptomarket.exchange.client import Client as cryptomkt
from cryptomarket.exchange.error import InvalidRequestError, AuthenticationError, RateLimitExceededError



number_of_attempts = 15


def is_not_local_exception(exception):
    return not isinstance(exception, (not_enough_balance, amount_must_be_greater, stuck_order))


class Cryptomkt(ExchangeClient):

    def __init__(self, public, secret):
        self.name = 'Cryptomarket'
        super().__init__()
        self._base_client = cryptomkt(public, secret)
        self.socket = self._base_client.get_socket()
        self.socket.logger.disabled = True
        self.socket.on('open-book', self._handle_socket_orderbook)
        self.socket.on('balance', self._handle_socket_balance)
        self.api_type = 'SOCKET'
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
        self.socket.subscribe(pair.ticker)

        if self.api_type == 'REST':
            self.__start_threads__(pair)

    def unsubscribe(self, pair):
        self.socket.unsubscribe(pair.ticker)
        pass

    def get_book(self, pair):
        raise NotImplementedError("Use sockets.")

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

    def get_ticker(self):
        pass

    def get_list_of_currencies_and_pairs(self):
        raise not_supported("This exchange doesn't have the endpoints to build the pairs automatically, "
                            "please initialize the PairManager() class the keyword list_of_pairs= and a list of "
                            "the pairs you want to implement")

    def get_history(self, pair):
        pass