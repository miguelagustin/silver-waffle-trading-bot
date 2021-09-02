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


class TestExchangeClient(unittest.TestCase):
    clients = []

    def test_toggle(self):
        for client in exchanges:
            with self.subTest(client=client):
                pair = random.choice(list(client.pairs))
                pair.enable()
                pair.disable()

    def test_orderbook_daemon(self):
        for client in exchanges:
            with self.subTest(client=client):
                for _ in range(5):
                    pair = random.choice(list(client.pairs))
                    print(f"Testing {client.name}:{pair.ticker}")
                    pair.enable()
                    time.sleep(5)
                    self.assertIsNotNone(pair.orderbook[ASK]._orders)
                    self.assertIsNotNone(pair.orderbook[BID]._orders)
                    pair.disable()

    def test_book_fetch(self):
        for client in exchanges:
            with self.subTest(client=client):
                print(f"Testing {client.name}")
                pair = random.choice(list(client.pairs))
                response = client.get_book(pair)
                self.assertTrue(response[ASK])
                self.assertTrue(response[BID])
