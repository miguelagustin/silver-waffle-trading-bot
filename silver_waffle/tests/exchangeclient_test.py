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
            pair = random.choice(list(client.pairs))
            pair.enable()
            pair.disable()
    def test_orderbook_daemon(self):
        for client in exchanges:
            for _ in range(10):
                pair = random.choice(list(client.pairs))
                print(f"Testing {client.name}:{pair.ticker}")
                pair.enable()
                time.sleep(3)
                self.assertTrue(pair.orderbook)
    def test_book_fetch(self):
        for client in exchanges:
            print(f"Testing {client.name}")
            pair = random.choice(list(client.pairs))
            response = client.get_book(pair)
            self.assertTrue(response[ASK])
            self.assertTrue(response[BID])
