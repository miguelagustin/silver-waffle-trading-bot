class Credential:
    """
    Class to store exchange credentials
    """
    all_credentials = []

    def __init__(self, *, secret_key, public_key, exchange_name):
        self.secret_key = secret_key
        self.public_key = public_key
        self.exchange_name = exchange_name
        self.all_credentials.append(self)

    def to_ccxt_credential(self):
        return {
            'apiKey': self.public_key,
            'secret': self.secret_key
        }

    def __repr__(self):
        return f'Credential(exchange_name={self.exchange_name})'


def find_credentials_by_exchange_name(exchange_name):
    results = []
    for credential in Credential.all_credentials:
        if credential.exchange_name == exchange_name:
            results.append(credential)
    return results


# Add your credentials to this file if you want them automatically recognized and for tests to work properly

Credential(public_key='your public key', secret_key='your secret key', exchange_name='your exchange name')
