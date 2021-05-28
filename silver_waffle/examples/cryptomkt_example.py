from silver_waffle.base.exchange import Pair, Currency, ee
from silver_waffle.base.side import ASK, BID
from silver_waffle.manager import PairManager
import silver_waffle.exchanges.cryptomkt as Cryptomkt
from silver_waffle.ui import Menu

cryptomkt = Cryptomkt.Cryptomkt()  # Instantiate the client with read only capabilities
cryptomkt.update_book_if_balance_is_empty = True


# We subscribe to the 'book_changed' event that occurs whenever the orderbook gets updated
@ee.on('book_changed')
def handle_orderbook_update(*args):
    print("The orderbook changed!")
    pair = args[0]
    pair.orderbook.__repr__()


pm = PairManager()
menu = Menu(pm.pairs)
menu()
