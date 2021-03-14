from trading_bot.base.exchange import Pair, Currency, Cryptocurrency, ee
from trading_bot.base.side import ASK, BID
from trading_bot.manager import PairManager
import trading_bot.exchanges.cryptomkt as Cryptomkt
from trading_bot.ui import Menu

public_key = input('Enter your public key: ')
secret_key = input('Enter your private key: ')

cryptomkt = Cryptomkt.Cryptomkt(public_key, secret_key)
cryptomkt.update_book_if_balance_is_empty = False

# Since cryptomarket doesn't have the api endpoints to auto define the pairs, this has to be done manually.
ars = Currency(name='Argentinian Peso', symbol='ars', exchange_client=cryptomkt)
eth = Cryptocurrency(name='Ethereum', symbol='eth', exchange_client=cryptomkt)
xlm = Cryptocurrency(name='Stellar', symbol='xlm', exchange_client=cryptomkt)
eos = Cryptocurrency(name='EOS', symbol='eos', exchange_client=cryptomkt)
btc = Cryptocurrency(name='Bitcoin', symbol='btc', exchange_client=cryptomkt)

ethars = Pair(exchange_client=cryptomkt, ticker='ETHARS', base=eth, quote=ars, minimum_step=2)
xlmars = Pair(exchange_client=cryptomkt, ticker='XLMARS', base=xlm, quote=ars, minimum_step=0.005)
eosars = Pair(exchange_client=cryptomkt, ticker='EOSARS', base=eos, quote=ars, minimum_step=0.05)
btcars = Pair(exchange_client=cryptomkt, ticker='BTCARS', base=btc, quote=ars, minimum_step=20)

list_of_pairs = [ethars, xlmars, eosars, btcars]

# We subscribe to the 'book_changed' event that occurs whenever the orderbook gets updated
@ee.on('book_changed')
def handle_orderbook_update(*args):
    print("The orderbook changed!")
    pair = args[0]
    pair.orderbook.__repr__()

pm = PairManager(list_of_pairs=list_of_pairs)
menu = Menu(list_of_pairs)
menu()
