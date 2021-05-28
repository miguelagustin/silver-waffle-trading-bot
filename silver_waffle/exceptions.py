class not_enough_balance(Exception):
    pass


class amount_must_be_greater(Exception):
    pass


class stuck_order(Exception):
    pass


class server_error(Exception):
    pass


class currency_doesnt_exist(Exception):
    pass


class not_supported(Exception):
    def __init__(self, message):
        self.message = message

    def __repr__(self):
        return f"not_supported({self.message})"
