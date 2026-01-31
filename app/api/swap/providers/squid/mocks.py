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

# Mock Squid route response for native ETH with bridge fee in tx value
# Uses hex values to test Amount class parsing
# tx value (1.02 ETH) > fromAmount (1 ETH), excess 0.02 ETH is bridge fee
MOCK_SQUID_ROUTE_NATIVE_WITH_BRIDGE_FEE = {
    "route": {
        "estimate": {
            "actions": [
                {
                    "fromToken": {
                        "symbol": "ETH",
                        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                        "chainId": "1",
                        "decimals": 18,
                    },
                    "toToken": {
                        "symbol": "USDC",
                        "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                        "chainId": "42161",
                        "decimals": 6,
                    },
                    "fromAmount": "0xde0b6b3a7640000",  # 1 ETH in hex
                    "toAmount": "1850000000",
                    "provider": "Squid Bridge",
                }
            ],
            "fromAmount": "0xde0b6b3a7640000",  # 1 ETH in hex
            "toAmount": "1850000000",
            "toAmountMin": "1831500000",
            "estimatedRouteDuration": 180,
            "aggregateSlippage": 1.0,
            "aggregatePriceImpact": "0.5",
            "gasCosts": [
                {
                    "type": "executeCall",
                    "token": {
                        "chainId": "1",
                        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                        "symbol": "ETH",
                        "decimals": 18,
                    },
                    "amount": "0x6a94d74f430000",  # 0.03 ETH in hex
                    "gasLimit": "300000",
                },
            ],
        },
        "transactionRequest": {
            "target": "0xce16F69375520ab01377ce7B88f5BA8C48F8D666",
            "data": "0x1234567890abcdef",
            "value": "0xe27c49886e60000",  # 1.02 ETH in hex (0.02 ETH excess)
            "gasLimit": "300000",
        },
        "quoteId": "squid-quote-native-bridge-fee",
    }
}

# Mock Squid route response for ERC20 (USDC) source with bridge fee in tx value
MOCK_SQUID_ROUTE_ERC20_WITH_BRIDGE_FEE = {
    "route": {
        "estimate": {
            "actions": [
                {
                    "fromToken": {
                        "symbol": "USDC",
                        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                        "chainId": "1",
                        "decimals": 6,
                    },
                    "toToken": {
                        "symbol": "USDC",
                        "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                        "chainId": "42161",
                        "decimals": 6,
                    },
                    "fromAmount": "1000000000",
                    "toAmount": "999000000",
                    "provider": "Squid Bridge",
                }
            ],
            "fromAmount": "1000000000",  # 1000 USDC
            "toAmount": "999000000",
            "toAmountMin": "989000000",
            "estimatedRouteDuration": 180,
            "aggregateSlippage": 1.0,
            "aggregatePriceImpact": "0.1",
            "gasCosts": [
                {
                    "type": "executeCall",
                    "token": {
                        "chainId": "1",
                        "address": "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                        "symbol": "ETH",
                        "decimals": 18,
                    },
                    "amount": "30000000000000000",  # 0.03 ETH gas
                    "gasLimit": "300000",
                },
            ],
        },
        "transactionRequest": {
            "target": "0xce16F69375520ab01377ce7B88f5BA8C48F8D666",
            "data": "0x1234567890abcdef",
            "value": "20000000000000000",  # 0.02 ETH bridge fee (entire value is fee for ERC20)
            "gasLimit": "300000",
        },
        "quoteId": "squid-quote-erc20-bridge-fee",
    }
}
