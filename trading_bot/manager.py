from base.side import ASK, BID
from ordered_set import OrderedSet
import base.exchange

class PairManager:
    def __init__(self, exchange_client=None, list_of_pairs=None):
        self.exchange_client = exchange_client
        if not list_of_pairs:
            self._get_and_set_pair_list()
        else:
            self.currencies = OrderedSet()
            for pair in list_of_pairs:
                self.currencies.add(pair.quote)
                self.currencies.add(pair.base)
            self.pairs = OrderedSet(list_of_pairs)
        self.currencies_in_use = dict.fromkeys(self.currencies, 0)
        self.currency_offset = dict.fromkeys(self.currencies, 0)
        self.amounts = {}
        self.set_amounts()

    def set_offset(self, currency, offset):
        self.currency_offset[currency] = offset
        self.set_amounts()

    def set_amounts(self):
        active_pairs = self.get_active_pairs()
        currencies_in_use = dict.fromkeys(self.currencies, 0)
        for pair in active_pairs:
            if pair.status[ASK]:
                currencies_in_use[pair.quote] += 1
            if pair.status[BID]:
                currencies_in_use[pair.base] += 1
        self.currencies_in_use = currencies_in_use
        self.amounts = dict.fromkeys(self.currencies, 0)
        for currency in self.currencies:
            try:
                self.amounts[currency] = (currency.balance['total_balance'] - self.currency_offset[currency]) / \
                                         currencies_in_use[currency]
            except ZeroDivisionError:
                self.amounts[currency] = currency.balance['total_balance']

    def get_active_pairs(self):
        active_pairs = []
        for pair in self.pairs:
            if pair.status[ASK] or pair.status[BID]:
                active_pairs.append(pair)
        return active_pairs

    def cancel_orders(self, currency):
        for pair in self.pairs:
            if pair.quote is currency:
                pair.update_active_orders()
                pair.cancel_orders(ASK)
            if pair.base is currency:
                pair.update_active_orders()
                pair.cancel_orders(BID)

    def _get_and_set_pair_list(self):
        currencies, pairs = self.exchange_client.get_list_of_currencies_and_pairs()
        self.currencies = OrderedSet(currencies)
        self.pairs = OrderedSet(pairs)

    def get_currency_by_symbol(self, symbol) -> base.exchange.Currency:
        for curr in self.currencies:
            if curr.symbol.lower() == symbol.lower():
                return curr

    def get_pair_by_ticker(self, ticker) -> base.exchange.Pair:
        for pair in self.pairs:
            if pair.ticker.lower() == ticker.lower():
                return pair

    def get_amount(self, pair):
        pass
