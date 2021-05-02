from __future__ import annotations
from pymitter import EventEmitter
import threading
from time import time
from money import Money
import cryptocompare
import trading_bot.ui as ui
from .side import ASK, BID
from .constants import STABLECOIN_SYMBOLS
from trading_bot.utilities import truncate

thread_lock = threading.Lock()
ee = EventEmitter()


def check_read_only(exchange_client):
    def decorator(function):
        def wrapper(*args, **kwargs):
            if exchange_client.read_only is False:
                result = function(*args, **kwargs)
                return result
        return wrapper
    return decorator


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
    def __init__(self, side, pair):
        self.side = side
        self.pair = pair
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

    def check_if_book_changed(self, new_book):
        if self._orders:
            if not any(x != y for x, y in zip(self._orders, new_book)):  # if book data is equal
                return False
        return True

    def set_orders(self, book):
        self._orders = book

    def get_order_above(self, amount_threshold):
        for order in self:
            if order.amount < amount_threshold / self.pair.base.global_price:
                continue
            if self.pair.orders[self.side] and order.price == self.pair.orders[self.side][0].price:
                continue
            return order

class Orderbook:
    def __init__(self, pair):
        self.orders = {ASK: OrderbookSide(ASK, pair), BID: OrderbookSide(BID, pair), 'updated_id': None}
        self.pair = pair

    def get_orders_above(self, amount_threshold):
        results = {ASK: self.orders[ASK].get_order_above(amount_threshold),
                   BID: self.orders[BID].get_order_above(amount_threshold)}
        return results

    def __getitem__(self, key):
        return self.orders[key]

    def __repr__(self):
        ui.print_orderbook(self)
        return ''


    # def get_first_order_above(self, amount, side = None):
    #     if side is None:


    def update(self, book):
        if not (ASK in book and BID in book):
            raise ValueError('Mising data in book')

        ask_changed = self.orders[ASK].check_if_book_changed(book[ASK])
        bid_changed = self.orders[BID].check_if_book_changed(book[BID])

        if ask_changed or bid_changed:
            self.orders[ASK].set_orders(book[ASK])
            self.orders[BID].set_orders(book[BID])
            ee.emit('book_changed', self.pair)

class Currency:
    def __init__(self, *, name, symbol, exchange_client):
        self.name = name
        self.exchange_client = exchange_client
        self.symbol = symbol
        self._balance = {}
        self.update_balance()
        self.update_global_price()
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
        if self.exchange_client.read_only is True:
            return
        new_balance = self.exchange_client.get_balance(self)
        self._set_balance(new_balance, currency=currency)
        ee.emit("updated_balance")

    def subscribe(self):
        pass

    def balance_is_empty(self):
        if self.balance['total_balance'].amount < float(self.empty_value.amount) * 1/self.global_price:
            ee.emit('balance_is_empty')
            return True
        else:
            return False

    def has_an_active_pair(self):
        for pair in self.base_pairs + self.quote_pairs:
            if pair:
                return True
        return False

    def update_global_price(self):
        self.global_price = self.get_global_price()

    def get_global_price(self):
        return cryptocompare.get_price(self.symbol, currency='USD')[self.symbol.upper()]['USD']

    def __repr__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not (self == other)

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

    def set_side_status(self, side: Side, new_status: bool, _launch_event = True) -> None:
        self.status[side] = new_status
        if new_status is True:
            self.exchange_client.subscribe(self)
        elif new_status is False and self.status[side.get_opposite()] is False:
            self.exchange_client.unsubscribe(self)

        self.update_active_orders()
        self.cancel_orders(side)
        self.quote.update_balance()
        self.base.update_balance()
        if _launch_event:
            ee.emit('status_changed', self)

    def toggle_side_status(self, side: Side):
        self.set_side_status(side, False if self.status[side] is True else True)

    def update_active_orders(self):
        if self.exchange_client.read_only is True:
            return
        result = self.exchange_client.get_active_orders(self)
        self.orders[ASK] = sorted(result[ASK])
        self.orders[BID] = sorted(result[BID])

    def create_limit_order(self, amount=None, side=None, limit_price=None):
        if self.exchange_client.read_only is True:
            return
        assert amount and side and limit_price
        order = self.exchange_client.create_order(self, amount, side, limit_price=limit_price)
        if order:
            self.orders[order.side].append(order)
            return order

    def create_market_order(self, amount=None, side=None):
        if self.exchange_client.read_only is True:
            return
        assert amount and side
        self.exchange_client.create_order(self, amount, side)

    def cancel_order(self, order):
        if self.exchange_client.read_only is True:
            return
        self.exchange_client.cancel_order(order)
        try:
            self.orders[order.side].remove(order)
        except ValueError:
            pass

    def cancel_orders(self, side):
        if self.exchange_client.read_only is True:
            return
        while self.orders[side]:
            for order in self.orders[side]:
                self.cancel_order(order)

    def _change_side(self, new_status):
        self.set_side_status(ASK, new_status, _launch_event=False)
        self.set_side_status(BID, new_status, _launch_event=False)
        ee.emit('status_changed', self)

    def enable(self):
        self._change_side(True)

    def disable(self):
        self._change_side(False)

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
