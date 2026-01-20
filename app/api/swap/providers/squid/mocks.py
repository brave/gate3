from app.api.common.models import Chain, TokenInfo, TokenSource, TokenType

# Mock token data
ETH_ON_ETHEREUM_TOKEN_INFO = TokenInfo(
    coin=Chain.ETHEREUM.coin,
    chain_id=Chain.ETHEREUM.chain_id,
    address=None,  # Native ETH
    name="Ethereum",
    symbol="ETH",
    decimals=18,
    logo=None,
    sources=[TokenSource.COINGECKO],
    token_type=TokenType.ERC20,
)

USDC_ON_ETHEREUM_TOKEN_INFO = TokenInfo(
    coin=Chain.ETHEREUM.coin,
    chain_id=Chain.ETHEREUM.chain_id,
    address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    name="USD Coin",
    symbol="USDC",
    decimals=6,
    logo=None,
    sources=[TokenSource.COINGECKO],
    token_type=TokenType.ERC20,
)

ETH_ON_ARBITRUM_TOKEN_INFO = TokenInfo(
    coin=Chain.ARBITRUM.coin,
    chain_id=Chain.ARBITRUM.chain_id,
    address=None,  # Native ETH on Arbitrum
    name="Ethereum",
    symbol="ETH",
    decimals=18,
    logo=None,
    sources=[TokenSource.COINGECKO],
    token_type=TokenType.ERC20,
)

USDC_ON_ARBITRUM_TOKEN_INFO = TokenInfo(
    coin=Chain.ARBITRUM.coin,
    chain_id=Chain.ARBITRUM.chain_id,
    address="0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    name="USD Coin",
    symbol="USDC",
    decimals=6,
    logo=None,
    sources=[TokenSource.COINGECKO],
    token_type=TokenType.ERC20,
)

# Mock Squid route response (ETH on Ethereum -> USDC on Arbitrum)
MOCK_SQUID_ROUTE_RESPONSE = {
    "route": {
        "estimate": {
            "actions": [
                {
                    "fromToken": {
                        "symbol": "ETH",
                        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                        "chainId": "1",
                        "decimals": 18,
                        "logoURI": "https://example.com/eth.svg",
                    },
                    "toToken": {
                        "symbol": "USDC",
                        "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                        "chainId": "42161",
                        "decimals": 6,
                        "logoURI": "https://example.com/usdc.svg",
                    },
                    "fromAmount": "1000000000000000000",
                    "toAmount": "1850000000",
                    "provider": "Squid Bridge",
                    "logoURI": "https://example.com/squid.svg",
                }
            ],
            "fromAmount": "1000000000000000000",  # 1 ETH
            "toAmount": "1850000000",  # ~1850 USDC
            "toAmountMin": "1831500000",  # After 1% slippage
            "estimatedRouteDuration": 180,  # 3 minutes
            "aggregateSlippage": 1.0,  # 1% aggregate slippage
            "aggregatePriceImpact": "0.5",  # 0.5% price impact
            "gasCosts": [
                {
                    "type": "executeCall",
                    "token": {
                        "chainId": "1",
                        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                        "symbol": "ETH",
                        "decimals": 18,
                    },
                    "amount": "50000000000000000",  # 0.05 ETH
                    "gasLimit": "300000",
                    "amountUsd": "100.00",
                },
            ],
        },
        "transactionRequest": {
            "target": "0xce16F69375520ab01377ce7B88f5BA8C48F8D666",
            "data": "0x1234567890abcdef",
            "value": "1000000000000000000",
            "gasLimit": "300000",
            "gasPrice": "50000000000",
        },
        "quoteId": "squid-quote-12345abcde",
    }
}

# Mock Squid status response (success)
MOCK_SQUID_STATUS_SUCCESS = {
    "id": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    "status": "success",
    "squidTransactionStatus": "completed",
}

# Mock Squid status response (ongoing)
MOCK_SQUID_STATUS_ONGOING = {
    "id": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    "status": "ongoing",
    "squidTransactionStatus": "bridging",
}

# Mock Squid error response
MOCK_SQUID_ERROR_RESPONSE = {
    "message": "No route found for this pair",
    "error": "ROUTE_NOT_FOUND",
    "errors": [
        {"message": "Insufficient liquidity for this trade"},
    ],
}
