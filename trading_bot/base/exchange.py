from __future__ import annotations
from pymitter import EventEmitter
import threading
from time import time
from money import Money
import cryptocompare
import trading_bot.ui as ui
from .side import ASK, BID
from trading_bot.utilities import truncate


STABLECOIN_SYMBOLS = ['USDC', 'DAI', 'USDT', 'BUSD', 'TUSD', 'PAX', 'VAI']
thread_lock = threading.Lock()
ee = EventEmitter()

class Order:
    def __init__(self, price, side, amount, order_id=None, pair=None):
        self.side = side
        self.order_id = order_id
        self.price = float(price)
        self.amount = float(amount)
        self.total = float(truncate(float(price) * float(amount), 4))
        self.pair = pair

    def __nonzero__(self):
        return self.amount

    def __repr__(self):
        return f'Order amount: {self.amount}, price: {self.price}, side: {self.side}, pair: {self.pair.ticker if self.pair else "none"}'

    def __eq__(self, other):
        return other.price == self.price and other.amount == self.amount

    def __lt__(self, other):
        return other.price < self.price


class OrderbookSide:
    def __init__(self, side):
        self.side = side
        self._idx = 0
        self._orders = []

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [Order(order['price'], self.side, order['amount']) for order in self._orders[i]]
        else:
            order = self._orders[i]
            return Order(order['price'], self.side, order['amount'])

    def __len__(self):
        return len(self._orders)

    def __iter__(self):
        self._idx = 0
        return self

    def __next__(self):
        try:
            order = self._orders[self._idx]
            self._idx += 1
            return Order(order['price'], self.side, order['amount'])
        except IndexError:
            self._idx = 0
            raise StopIteration  # Done iterating.

    def __repr__(self):
        ui.print_side(self)
        return ''


class Orderbook:
    def __init__(self, pair):
        self.orders = {ASK: OrderbookSide(ASK), BID: OrderbookSide(BID), 'updated_id': None}
        self.pair = pair

    def __getitem__(self, key):
        return self.orders[key]

    def __repr__(self):
        ui.print_orderbook(self)
        return ''

    def update(self, book):
        if ASK in book:
            self.orders[ASK]._orders = book[ASK]
        if BID in book:
            self.orders[BID]._orders = book[BID]
        if 'updated_id' in book:
            if book['updated_id'] != self.orders['updated_id']:
                ee.emit("book_changed", self.pair)
                self.orders['updated_id'] = book['updated_id']
        else:
            ee.emit("book_changed", self.pair)


class Currency:
    def __init__(self, *, name, symbol, exchange_client):
        self.name = name
        self.exchange_client = exchange_client
        self.symbol = symbol
        self._balance = {}
        self.update_balance()
        self.empty_value = Money(10, currency='USD')
        # self.reserved_amount_mode = reserved_amount_mode
        self.quote_pairs = []  # pairs where this currency is quote
        self.base_pairs = []  # pairs where this currency is base
        self._exchange_rate_last_update = 0

    @property
    def balance(self):
        # self.update_balance()
        return self._balance

    def _set_balance(self, new_balance, currency=None):
        if currency is None:
            currency = self.symbol.upper()
        if currency in STABLECOIN_SYMBOLS:
            currency = 'USD'
        available_balance, locked_balance = new_balance
        locked_balance = Money(locked_balance, currency=currency)
        available_balance = Money(available_balance, currency=currency)
        self._balance = {'available_balance': available_balance, 'locked_balance': locked_balance,
                         'total_balance': locked_balance + available_balance}

    def update_balance(self, currency=None):
        new_balance = self.exchange_client.get_balance(self)
        self._set_balance(new_balance, currency=currency)
        ee.emit("updated_balance")

    def subscribe(self):
        pass

    def balance_is_empty(self):
        if time() - self._exchange_rate_last_update > 30:
            self._exchange_rate = cryptocompare.get_price('USD', currency=self.symbol)['USD'][self.symbol.upper()]
            self._exchange_rate_last_update = time()
        if self.balance['total_balance'].amount < float(self.empty_value.amount) * self._exchange_rate:
            ee.emit('balance_is_empty')
            return True
        else:
            return False

    def has_an_active_pair(self):
        for pair in self.base_pairs + self.quote_pairs:
            if pair:
                return True
        return False

    def __repr__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not (self == other)


class Cryptocurrency(Currency):
    def __init__(self, *, name, symbol, exchange_client):
        super().__init__(name=name, symbol=symbol, exchange_client=exchange_client)
        self.update_international_price()

    def update_international_price(self):
        self.international_price = self.get_international_price()

    def get_international_price(self):
        return cryptocompare.get_price(self.symbol, currency='USD')[self.symbol.upper()]['USD']

class Pair:
    def __init__(self, *, exchange_client: ExchangeClient, ticker: int, quote: Currency, base: Currency,
                 minimum_step: float):
        self.exchange_client = exchange_client
        self.base = base
        self.quote = quote
        self.orderbook = Orderbook(self)
        base.base_pairs.append(self)
        quote.quote_pairs.append(self)
        self.minimum_step = float(minimum_step)  # ex extra
        self.orders = {ASK: [], BID: []}
        self.status = {ASK: False, BID: False}
        self.ticker = ticker
        self.update_active_orders()
        self.cancel_orders(ASK)
        self.cancel_orders(BID)

    def set_side_status(self, side: Side, new_status: bool) -> None:
        self.status[side] = new_status
        if new_status is True:
            self.exchange_client.subscribe(self)
        elif new_status is False and self.status[side.get_opposite()] is False:
            self.exchange_client.unsubscribe(self)

        self.update_active_orders()
        self.cancel_orders(side)
        self.quote.update_balance()
        self.base.update_balance()
        ee.emit('status_changed', self)

    def toggle_side_status(self, side: Side):
        self.set_side_status(side, False if self.status[side] is True else True)

    def update_active_orders(self):
        result = self.exchange_client.get_active_orders(self)
        self.orders[ASK] = sorted(result[ASK])
        self.orders[BID] = sorted(result[BID])

    def create_limit_order(self, amount=None, side=None, limit_price=None):
        assert amount and side and limit_price
        order = self.exchange_client.create_order(self, amount, side, limit_price=limit_price)
        if order:
            self.orders[order.side].append(order)
            return order

    def create_market_order(self, amount=None, side=None):
        assert amount and side
        self.exchange_client.create_order(self, amount, side)

    def cancel_order(self, order):
        self.exchange_client.cancel_order(order)
        try:
            self.orders[order.side].remove(order)
        except ValueError:
            pass

    def cancel_orders(self, side):
        for order in self.orders[side]:
            self.cancel_order(order)

    def update_orderbook(self):
        self.orderbook.update(self.exchange_client.get_book(self))

    def __hash__(self):
        return hash((self.quote.name, self.base.name))

    def __eq__(self, other):
        return (self.quote.name, self.base.name) == (other.quote.name, self.base.name)

    def __ne__(self, other):
        return not (self == other)

    def __bool__(self):
        return self.status[BID] or self.status[ASK]

    def __repr__(self):
        return f"Pair(ticker={self.ticker}, exchange_client={self.exchange_client}, quote={self.quote}, base={self.base}, minimum_step={self.minimum_step}) "
