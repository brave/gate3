from .constants import ZERO_EX_NATIVE_TOKEN_ADDRESS

MOCK_ZERO_EX_QUOTE_RESPONSE = {
    "blockNumber": "210000000",
    "buyAmount": "1850000000",
    "buyToken": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "fees": {
        "integratorFee": None,
        "zeroExFee": None,
        "gasFee": None,
    },
    "gas": "250000",
    "gasPrice": "100000000",
    "issues": {
        "allowance": None,
        "balance": None,
        "simulationIncomplete": False,
        "invalidSourcesPassed": [],
    },
    "liquidityAvailable": True,
    "minBuyAmount": "1840750000",
    "route": {
        "fills": [
            {
                "from": ZERO_EX_NATIVE_TOKEN_ADDRESS,
                "to": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "source": "Uniswap_V3",
                "proportionBps": "7000",
            },
            {
                "from": ZERO_EX_NATIVE_TOKEN_ADDRESS,
                "to": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "source": "Curve",
                "proportionBps": "3000",
            },
        ],
        "tokens": [
            {
                "address": ZERO_EX_NATIVE_TOKEN_ADDRESS,
                "symbol": "ETH",
            },
            {
                "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "symbol": "USDC",
            },
        ],
    },
    "sellAmount": "1000000000000000000",
    "sellToken": ZERO_EX_NATIVE_TOKEN_ADDRESS,
    "tokenMetadata": {},
    "totalNetworkFee": "25000000000000000",
    "transaction": {
        "to": "0x0000000000001fF3684f28c67538d4D072C22734",
        "data": "0xdeadbeefcafe",
        "gas": "250000",
        "gasPrice": "100000000",
        "value": "1000000000000000000",
    },
    "zid": "0x-zid-abc123",
}


MOCK_ZERO_EX_QUOTE_ERC20_RESPONSE = {
    "buyAmount": "1000000",
    "buyToken": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "gas": "250000",
    "gasPrice": "100000000",
    "issues": {
        "allowance": {
            "actual": "0",
            "spender": "0x0000000000001fF3684f28c67538d4D072C22734",
        },
        "balance": None,
    },
    "liquidityAvailable": True,
    "minBuyAmount": "990000",
    "route": {
        "fills": [
            {
                "source": "Uniswap_V3",
                "proportionBps": "10000",
            }
        ],
        "tokens": [],
    },
    "sellAmount": "1000000",
    "sellToken": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "totalNetworkFee": "25000000000000000",
    "transaction": {
        "to": "0x0000000000001fF3684f28c67538d4D072C22734",
        "data": "0xabcdef",
        "gas": "250000",
        "gasPrice": "100000000",
        "value": "0",
    },
}


MOCK_ZERO_EX_ERROR_404 = {
    "name": "INSUFFICIENT_LIQUIDITY",
    "message": "No route found for the requested swap",
}

MOCK_ZERO_EX_ERROR_429 = {
    "name": "RATE_LIMITED",
    "message": "Too many requests",
}

MOCK_ZERO_EX_ERROR_VALIDATION = {
    "name": "VALIDATION_FAILED",
    "message": "sellAmount must be a positive integer",
}

MOCK_ZERO_EX_NO_LIQUIDITY_RESPONSE = {
    "liquidityAvailable": False,
    "zid": "0x-zid-no-liq",
}

MOCK_ALCHEMY_RECEIPT_SUCCESS = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "status": "0x1",
        "transactionHash": "0xabc123",
        "blockNumber": "0xd00",
    },
}

MOCK_ALCHEMY_RECEIPT_FAILED = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "status": "0x0",
        "transactionHash": "0xabc123",
        "blockNumber": "0xd00",
    },
}

MOCK_ALCHEMY_RECEIPT_NULL = {
    "jsonrpc": "2.0",
    "id": 1,
    "result": None,
}
