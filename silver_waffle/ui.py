from colorama import Fore, Back, Style, init
import os
from utilities import truncate
import platform
from silver_waffle.base.side import ASK, BID

init(autoreset=True, convert=True if platform.system() == 'Windows' else False) # this is so that colors work on Linux and Windows
def print_side(orderbook):
    if len(orderbook) == 0:
        print([])
        return
    color = Fore.RED if orderbook.side == ASK else Fore.GREEN
    _format = color + '{0:>0.2f}' + '{1:>10} {2:>12}'
    for count, order in enumerate(reversed(orderbook[0:10]) if orderbook.side is ASK else orderbook):
        print(_format.format(order.price, truncate(order.amount,2), order.total))
        if count == 9:
            break
def print_orderbook(orderbook):
    if len(orderbook[ASK]) == 0 or len(orderbook[BID]) == 0:
        print([])
        return
    print_side(orderbook[ASK])
    print('{0:<5} {1:>26}'.format('----', round(float(orderbook[ASK][0].price) - float(orderbook[BID][0].price),2)))
    print_side(orderbook[BID])


class Menu:
    def __init__(self, list_of_pairs):
        self.string = '{} - {:9} {} {}'
        self.pairs = list(list_of_pairs)

    def __call__(self, clear=False):
        while True:
            option_menu = 0
            if clear:
                os.system('clear')
            for pair in self.pairs:
                print(self.string.format(option_menu, pair.ticker.lower(), 'BID ', Fore.BLACK + (
                    Back.GREEN + 'enabled' if pair.status[BID] else Back.RED + 'disabled')))
                option_menu += 1
                print(self.string.format(option_menu, pair.ticker.lower(), 'ASK ', Fore.BLACK + (
                    Back.GREEN + 'enabled' if pair.status[ASK] else Back.RED + 'disabled')))
                option_menu += 1
            print('{} - start'.format(option_menu))
            selection = input()
            if selection == 'da' or selection == 'ea':
                for pair in self.pairs:
                    pair.set_side_status(ASK, False if selection == 'da' else True)
                    pair.set_side_status(BID, False if selection == 'da' else True)
            try:
                selection = int(selection)
            except ValueError:
                continue
            if selection == option_menu:
                break
            if selection > option_menu:
                continue
            if selection % 2 == 0:
                self.pairs[int(selection / 2)].toggle_side_status(BID)
            elif selection % 2 == 1:
                self.pairs[int(selection / 2)].toggle_side_status(ASK)
