import operator
import exceptions
import base
import ctypes
import sys, os
from trading_bot.base.constants import FIAT_SYMBOLS


def get_truth(inp, relate, out):
    ops = {'>': operator.gt,
           '<': operator.lt,
           '>=': operator.ge,
           '<=': operator.le,
           '==': operator.eq}
    return ops[relate](inp, out)


def get_result(inp, relate, out):
    ops = {'-': operator.sub,
           '+': operator.add}
    return ops[relate](inp, out)

def truncate(f, n):
    '''Truncates/pads a float f to n decimal places without rounding'''
    s = '{}'.format(f)
    if 'e' in s or 'E' in s:
        return '{0:.{1}f}'.format(f, n)
    i, p, d = s.partition('.')
    return '.'.join([i, (d + '0' * n)[:n]])


def sum_first_n_orders(n, orderbook_side):
    total_amount = 0
    for count, order in enumerate(orderbook_side):
        total_amount += order.amount
        if count == n - 1:
            break
    return total_amount


def market_order(pair, amount, side):
    if amount == 'all':
        amount = pair.quote.balance['total_balance']
        print(pair.quote.balance)
        if amount < 1:
            return
    else:
        amount = float(amount)
    try:
        with base.thread_lock:
            pair.cancel_orders(side)
            pair.create_market_order(amount=amount, side=side)
    except exceptions.not_enough_balance:
        return


def terminate_thread(thread):
    """Terminates a python thread from another thread.

    :param thread: a threading.Thread instance
    """
    if not thread.is_alive():
        return

    exc = ctypes.py_object(SystemExit)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_long(thread.ident), exc)
    if res == 0:
        raise ValueError("nonexistent thread id")
    elif res > 1:
        # """if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"""
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")

def _is_symbol_a_cryptocurrency(self, symbol: str):
    return False if symbol in FIAT_SYMBOLS else True

# Disable
def block_print():
    sys.stdout = open(os.devnull, 'w')

# Restore
def unblock_print():
    sys.stdout = sys.__stdout__