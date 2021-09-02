from __future__ import annotations
from pymitter import EventEmitter
import threading
import money
import cryptocompare
import silver_waffle.ui as ui
from silver_waffle.base.side import ASK, BID
from silver_waffle.base.constants import STABLECOIN_SYMBOLS
from silver_waffle.utilities import truncate, get_truth, _is_symbol_a_cryptocurrency
from silver_waffle.base.exchange_rate_feeds import get_chainlink_price, get_ars_criptoya
import google_currency
import json
import re
import ccxt
# We change money's currency regex in order for it to support a wider range of tickers
money.money.REGEX_CURRENCY_CODE = re.compile("^[A-Z]{2,10}$")

thread_lock = threading.Lock()
ee = EventEmitter()
google_currency.logger.disabled = True
binance_oracle = ccxt.binance()


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
        self._orders = None

    def __getitem__(self, i):
        # we lazily create the Order objects to save CPU cycles
        if isinstance(i, slice):
            return [Order(order['price'], self.side, order['amount'], pair=self.pair) for order in self._orders[i]]
        else:
            order = self._orders[i]
            return Order(order['price'], self.side, order['amount'], pair=self.pair)

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

    def __bool__(self):
        return True if self._orders else False

    def check_if_book_changed(self, new_book):
        if self._orders:
            if not any(x != y for x, y in zip(self._orders, new_book)):  # if book data is equal
                return False
        return True

    def set_orders(self, book):
        self._orders = book

    def get_order_above(self, amount_threshold):
        """ Returns the first order found with an amount higher than amount_threshold, excluding your own orders"""
        for order in self:
            if order.amount < amount_threshold / self.pair.base.global_price:
                continue
            if self.pair.orders[self.side] and order.price == self.pair.orders[self.side][0].price:
                continue
            return order

    def get_orders_up_until(self, price_threshold):
        """ Returns all the orders found with a price higher or lower (depends on the side) than price_threshold"""
        results = []
        for order in self:
            if get_truth(order.price, '<' if self.side == ASK else '>', price_threshold):
                results.append(order)
            else:
                break
        return results


class Orderbook:
    def __init__(self, pair):
        self.orders = {ASK: OrderbookSide(ASK, pair), BID: OrderbookSide(BID, pair), 'updated_id': None}
        self.pair = pair
        self._check_book = True

    def get_orders_above(self, amount_threshold):
        results = {ASK: self.orders[ASK].get_order_above(amount_threshold),
                   BID: self.orders[BID].get_order_above(amount_threshold)}
        return results

    def get_liquidity(self, percentage_from_midpoint=0.04):
        first_ask = self.orders[ASK].get_order_above(60)
        first_bid = self.orders[BID].get_order_above(60)

        midpoint = first_bid.price + (first_ask.price - first_bid.price)/2

        orders = {ASK: self.orders[ASK].get_orders_up_until(midpoint * (1 + percentage_from_midpoint)),
                  BID: self.orders[BID].get_orders_up_until(midpoint * (1 - percentage_from_midpoint))}

        results = {ASK: None, BID: None}
        for side in [ASK, BID]:
            total_amount = 0
            for order in orders[side]:
                total_amount += order.amount
            results[side] = total_amount
        return results

    def get_spread(self, amount_threshold=0):
        first_ask = self.orders[ASK].get_order_above(amount_threshold)
        first_bid = self.orders[BID].get_order_above(amount_threshold)
        return (first_ask.price - first_bid.price)/first_ask.price

    def __getitem__(self, key):
        if isinstance(key, str):
            if key.upper() == 'ASK' or key.upper() == 'SELL':
                return self.orders[ASK]
            elif key.upper() == 'BID' or key.upper() == 'BUY':
                return self.orders[BID]
        elif key is ASK or key is BID:
            return self.orders[key]
        else:
            raise IndexError

    def __repr__(self):
        try:
            ui.print_orderbook(self)
        except TypeError:
            print('[]')
        return ''

    def __bool__(self):
        return bool(self.orders[ASK]) and bool(self.orders[BID])

    def update(self, book):
        if not (ASK in book and BID in book):
            raise ValueError('Mising data in book')
        if self._check_book is True:
            ask_changed = self.orders[ASK].check_if_book_changed(book[ASK])
            bid_changed = self.orders[BID].check_if_book_changed(book[BID])

            if ask_changed or bid_changed:
                self.orders[ASK].set_orders(book[ASK])
                self.orders[BID].set_orders(book[BID])
                ee.emit('book_changed', self.pair)
        elif self._check_book is False:
            self.orders[ASK].set_orders(book[ASK])
            self.orders[BID].set_orders(book[BID])


class Currency:
    def __init__(self, *, name, symbol, exchange_client):
        if not name:
            raise ValueError('invalid name')
        self.name = name
        self.exchange_client = exchange_client
        self.symbol = symbol
        self._balance = {'available_balance':None, 'locked_balance': None, 'total_balance': None}
        # self.update_balance()
        self.global_price = 0
        self.update_balance()
        self.update_global_price()
        self.empty_value = money.Money(20, currency='USD')
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
        locked_balance = money.Money(locked_balance, currency=currency)
        available_balance = money.Money(available_balance, currency=currency)
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
        """Returns True if the currency balance is empty (and emits a 'balance_is_empty' event), False if it isn't"""
        if self.balance['total_balance'].amount < float(self.empty_value.amount) * 1/self.global_price:
            ee.emit('balance_is_empty')
            return True
        else:
            return False

    def has_an_active_pair(self):
        """Returns True if there are >0 pairs enabled, False if there aren't"""
        for pair in self.base_pairs + self.quote_pairs:
            if pair:
                return True
        return False

    def update_global_price(self):
        try:
            self.global_price = self.get_global_price()
        except Exception:
            self.global_price = 0

    def get_global_price(self):
        """Gets how much this currency is worth, in terms of 1 USD."""
        if self.symbol.upper() in STABLECOIN_SYMBOLS or self.symbol.upper() == 'USD':
            return 1

        if not _is_symbol_a_cryptocurrency(self.symbol.upper()):
            #  Cryptocompare and Google don't know what's the actual free market ARS exchange rate
            #  https://en.wikipedia.org/wiki/Argentine_currency_controls_(2011%E2%80%932015)#Return_of_the_controls
            if self.symbol.upper() == 'ARS':
                price = get_ars_criptoya()
            result = json.loads(google_currency.convert(self.symbol, 'usd', 1))
            if result['converted'] is True:
                price = float(result['amount'])
            else:
                price = cryptocompare.get_price(self.symbol, currency='USD')[self.symbol.upper()]['USD']
        else:
            try:
                price = get_chainlink_price(self.symbol)
            except ValueError:
                try:
                    price = binance_oracle.fetch_ticker(f"{self.symbol.upper()}/USDT")['bid']
                except ccxt.base.errors.BadSymbol:
                    # Cryptocompare is used as a last resort because it has shitty rate limits
                    price = cryptocompare.get_price(self.symbol, currency='USD')[self.symbol.upper()]['USD']

        return price

    def to(self, currency):
        """Converts this currency to another one."""
        return currency.global_price/self.global_price

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

        # self.update_active_orders()
        # self.cancel_orders(ASK)
        # self.cancel_orders(BID)

    def set_side_status(self, side: Side, new_status: bool, _launch_event=True) -> None:
        """Sets the status of this pair. Each pair has two statuses, according to its two sides, BID and ASK.
        At least one side needs to be enabled in order for the orderbook and the pair currencies balance to be updated.
        It also determines the truth value of this object. If at least one side is enabled, the truth value of this object will be True.

        if pair: #will evaluate as True if at least one side is enabled.
            print("This pair is enabled")

        It also emits a 'status_changed' event whenever there is a change. This can be disabled by passing the keyword argument
        _launch_event as False.
        """
        self.status[side] = new_status
        if new_status is True:
            self.exchange_client.subscribe(self)
        elif new_status is False and self.status[side.get_opposite()] is False:
            self.exchange_client.unsubscribe(self)
            self.orderbook = Orderbook(self)

        self.update_active_orders()
        self.cancel_orders(side)
        self.quote.update_balance()
        self.base.update_balance()

        if _launch_event:
            ee.emit('status_changed', self)

    def toggle_side_status(self, side: Side):
        self.set_side_status(side, False if self.status[side] is True else True)

    def update_active_orders(self):
        """Updates the current active orders in the self.orders attribute"""
        if self.exchange_client.read_only is True:
            return
        result = self.exchange_client.get_active_orders(self)
        self.orders[ASK] = sorted(result[ASK])
        self.orders[BID] = sorted(result[BID])

    def create_limit_order(self, amount=None, side=None, limit_price=None) -> Order:
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
        """Cancels all the orders of the given side"""
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
        return hash(f"{self.quote.name}{self.base.name}")

    def __eq__(self, other):
        return (self.quote.name, self.base.name) == (other.quote.name, self.base.name)

    def __ne__(self, other):
        return not (self == other)

    def __bool__(self):
        return self.status[BID] or self.status[ASK]

    def __repr__(self):
        return f"Pair(ticker={self.ticker.upper()})"
