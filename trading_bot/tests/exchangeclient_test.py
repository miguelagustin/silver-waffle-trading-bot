import unittest
from exchanges.cryptomkt import Cryptomkt
from exchanges.buda import Buda

exchanges = [Buda, Cryptomkt]

if __name__ == '__main__':
    unittest.main()

class TestExchangeClient(unittest.TestCase):
    def __init__(self):
        self.exchanges = []
        for exchange in exchanges:
            self.exchanges.append(exchange())
    def test_book(self):
        for exchange in self.exchanges:
            self.assertTrue()