from web3 import Web3
from .constants import CHAINLINK_ADDRESSES, FREE_RPC_ENDPOINTS
import requests

def get_ars_criptoya():
    response = requests.get('https://criptoya.com/api/dolar')
    return response.json()['ccb']

def get_chainlink_price(symbol):
    """
    Uses python web3 and infura credentials to query chainlink mainnet pricefeed
    data for specified currency pair input.
    Parameters
    ----------
    ticker : TYPE
        DESCRIPTION.
    chain : TYPE, optional
        DESCRIPTION. The default is 'mainnet'.
    Raises
    ------
    ValueError
        DESCRIPTION.
    Returns
    -------
    price : float
        price in USD.
    timestamp : float
        UTC timestamp in seconds.
    """

    abi = '[{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"description","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint80","name":"_roundId","type":"uint80"}],"name":"getRoundData","outputs":[{"internalType":"uint80","name":"roundId","type":"uint80"},{"internalType":"int256","name":"answer","type":"int256"},{"internalType":"uint256","name":"startedAt","type":"uint256"},{"internalType":"uint256","name":"updatedAt","type":"uint256"},{"internalType":"uint80","name":"answeredInRound","type":"uint80"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"latestRoundData","outputs":[{"internalType":"uint80","name":"roundId","type":"uint80"},{"internalType":"int256","name":"answer","type":"int256"},{"internalType":"uint256","name":"startedAt","type":"uint256"},{"internalType":"uint256","name":"updatedAt","type":"uint256"},{"internalType":"uint80","name":"answeredInRound","type":"uint80"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"version","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]'
    for rpc in FREE_RPC_ENDPOINTS:
        try:
            web3 = Web3(Web3.HTTPProvider(rpc))
            break
        except Exception:
            continue


    key = symbol+'-USD'
    if key not in CHAINLINK_ADDRESSES:
        raise ValueError(f'{symbol.upper()} not available on chainlink')
    address = CHAINLINK_ADDRESSES[key]
    contract = web3.eth.contract(address=address, abi=abi)
    roundData = contract.functions.latestRoundData().call()
    price = roundData[1]
    timestamp = roundData[3]
    return price/1E8