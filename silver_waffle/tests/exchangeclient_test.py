import unittest
from silver_waffle.base.exchange_client import ExchangeClient
from silver_waffle.base.side import ASK, BID
import random
import time

if __name__ == '__main__':
    unittest.main()

clients = ['buda', 'ripio']
exchanges = []

for client in clients:
    print(f'creating {client}')
    exchanges.append(ExchangeClient(client))

for client in exchanges:
    assert client.pairs


def loop_through_exchanges(method):
    def call(self, *args, **kwargs):
        for client in exchanges:
            with self.subTest(client=client):
                method(self, client, *args, **kwargs)

    return call


class TestExchangeClient(unittest.TestCase):
    clients = []

    @loop_through_exchanges
    def test_toggle(self, client):
        pair = random.choice(list(client.pairs))
        pair.enable()
        pair.disable()

    @loop_through_exchanges
    def test_orderbook_daemon(self, client: ExchangeClient):
        for _ in range(5):
            pair = random.choice(list(client.pairs))
            print(f"Testing {client.name}:{pair.ticker}")
            pair.enable()
            time.sleep(5)
            self.assertIsNotNone(pair.orderbook[ASK]._orders)
            self.assertIsNotNone(pair.orderbook[BID]._orders)
            pair.disable()

    @loop_through_exchanges
    def test_book_fetch(self, client: ExchangeClient):
        print(f"Testing {client.name}")
        pair = random.choice(list(client.pairs))
        response = client.get_book(pair)
        self.assertTrue(response[ASK])
        self.assertTrue(response[BID])

    @loop_through_exchanges
    def test_get_balance(self, client: ExchangeClient):
        if client.read_only is True:
            print('Client is set as read only. This test cannot run.')
            return
        for _ in range(3):
            pair = random.choice(list(client.pairs))
            available, locked = client.get_balance(pair.base)
            self.assertTrue(isinstance(available, float) or isinstance(available, int))
            self.assertTrue(isinstance(locked, float) or isinstance(locked, int))

    @loop_through_exchanges
    def test_get_active_orders(self, client: ExchangeClient):
        if client.read_only is True:
            print('Client is set as read only. This test cannot run.')
            return
        for _ in range(3):
            pair = random.choice(list(client.pairs))
            orders = client.get_active_orders(pair)
            self.assertTrue(ASK in orders.keys())
            self.assertTrue(BID in orders.keys())
