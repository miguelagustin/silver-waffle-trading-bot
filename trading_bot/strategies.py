from base.exchange import thread_lock, Pair
from base.side import ASK, BID
from time import sleep, time
import logging
from utilities import get_result, get_truth, terminate_thread
from exceptions import not_enough_balance
from decimal import Decimal
from threading import Thread


class Auto:
    instances = []

    def __init__(self, pair: Pair, side):
        self.pair = pair
        self.side = side

    def stop(self):
        terminate_thread(self.thread)
        self.instances.remove(self)

    def start_thread(self, target):
        self.thread = Thread(target=target, args=[])
        self.thread.start()
        Auto.instances.append(self)

    def shutdown_in_minutes(self, minutes):
        def shutdown():
            sleep(minutes*60)
            self.stop()
        Thread(target=shutdown)


class AutoExecute(Auto):
    def __init__(self, *, pair: Pair, price, side):
        super().__init__(pair, side)
        self.price = float(price)
        self.start_thread(self.auto_execute)

    def currency_has_enough_balance(self, order):
        if self.side is BID:
            if self.pair.base.balance['total_balance'].amount > order.amount:
                return True
        elif self.side is ASK:
            if self.pair.quote.balance['total_balance'].amount/order.price > order.amount:
                return True
        else:
            return False

    def auto_execute(self):
        while True:
            order = self.pair.orderbook[self.side][0]
            if get_truth(order.price, '<' if self.side is ASK else '>', self.price):
                if not self.currency_has_enough_balance(order):
                    print("not enough balance to auto execute")
                    sleep(30)
                    continue
                with thread_lock:
                    self.pair.cancel_orders(self.side)
                    self.pair.cancel_orders(self.side.get_opposite())
                    order = self.pair.create_limit_order(amount=order.amount, limit_price=order.price,
                                                         side=self.side.get_opposite())
                    print(f"auto {'sold' if self.side is BID else 'bought'} {order.amount} at {order.price} ")
                    self.pair.cancel_order(order)
                sleep(5)
            sleep(5)

    def __repr__(self):
        return f"AutoExecute(pair={self.pair}, price={self.price}, side={self.side})"


class AutoMarket(Auto):
    def __init__(self, *, pair: Pair, side, cooldown, amount):
        super().__init__(pair, side)
        self.cooldown = cooldown
        self.amount = amount
        self.timestamp = time()
        self.start_thread(self.auto_market)

    def auto_market(self):
        while True:
            sleep(5)
            if (self.pair.quote if self.side is BID else self.pair.base).balance_is_empty():
                if time() - self.timestamp > self.cooldown:
                    with thread_lock:
                        self.pair.cancel_orders(self.side.get_opposite())
                        print(f"auto market {'sold' if self.side is BID else 'bought'} {self.amount}")
                        self.pair.create_market_order(amount=self.amount, side=self.side.get_opposite())
                        self.timestamp = time()

    def __repr__(self):
        return f"AutoMarket(pair={self.pair}, side={self.side}, cooldown={self.cooldown}, amount={self.amount})"