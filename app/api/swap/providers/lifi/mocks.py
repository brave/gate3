from app.api.common.models import Chain, TokenInfo, TokenSource, TokenType

ETH_ON_ETHEREUM_TOKEN_INFO = TokenInfo(
    coin=Chain.ETHEREUM.coin,
    chain_id=Chain.ETHEREUM.chain_id,
    address=None,
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
    address=None,
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

# Mock LI.FI quote response (ETH on Ethereum -> USDC on Arbitrum)
MOCK_LIFI_QUOTE_RESPONSE = {
    "id": "lifi-quote-12345abcde",
    "type": "lifi",
    "tool": "stargate",
    "toolDetails": {
        "key": "stargate",
        "name": "Stargate",
        "logoURI": "https://example.com/stargate.svg",
    },
    "action": {
        "fromChainId": 1,
        "toChainId": 42161,
        "fromToken": {
            "address": "0x0000000000000000000000000000000000000000",
            "chainId": 1,
            "symbol": "ETH",
            "decimals": 18,
            "name": "Ethereum",
            "logoURI": "https://example.com/eth.svg",
        },
        "toToken": {
            "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "chainId": 42161,
            "symbol": "USDC",
            "decimals": 6,
            "name": "USD Coin",
            "logoURI": "https://example.com/usdc.svg",
        },
        "fromAmount": "1000000000000000000",
        "slippage": 0.005,
        "fromAddress": "0x1234567890123456789012345678901234567890",
        "toAddress": "0x1234567890123456789012345678901234567890",
    },
    "estimate": {
        "tool": "stargate",
        "approvalAddress": "0xApprovalAddress1234567890123456789012345",
        "toAmount": "1850000000",
        "toAmountMin": "1840750000",
        "fromAmount": "1000000000000000000",
        "feeCosts": [
            {
                "name": "Bridge Fee",
                "description": "Fee for cross-chain bridging",
                "token": {
                    "address": "0x0000000000000000000000000000000000000000",
                    "chainId": 1,
                    "symbol": "ETH",
                    "decimals": 18,
                    "name": "Ethereum",
                },
                "amount": "5000000000000000",
                "amountUSD": "10.00",
                "percentage": "0.005",
                "included": True,
            }
        ],
        "gasCosts": [
            {
                "type": "SEND",
                "amount": "50000000000000000",
                "amountUSD": "100.00",
                "token": {
                    "address": "0x0000000000000000000000000000000000000000",
                    "chainId": 1,
                    "symbol": "ETH",
                    "decimals": 18,
                    "name": "Ethereum",
                },
                "estimate": "300000",
                "limit": "400000",
            }
        ],
        "executionDuration": 180,
        "fromAmountUSD": "2000.00",
        "toAmountUSD": "1850.00",
    },
    "includedSteps": [
        {
            "id": "step-1",
            "type": "swap",
            "tool": "uniswap",
            "toolDetails": {
                "key": "uniswap",
                "name": "Uniswap",
                "logoURI": "https://example.com/uniswap.svg",
            },
            "action": {
                "fromChainId": 1,
                "toChainId": 1,
                "fromToken": {
                    "address": "0x0000000000000000000000000000000000000000",
                    "chainId": 1,
                    "symbol": "ETH",
                    "decimals": 18,
                    "name": "Ethereum",
                },
                "toToken": {
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "chainId": 1,
                    "symbol": "USDC",
                    "decimals": 6,
                    "name": "USD Coin",
                },
                "fromAmount": "1000000000000000000",
                "slippage": 0.005,
                "fromAddress": "0x1234567890123456789012345678901234567890",
                "toAddress": "0x1234567890123456789012345678901234567890",
            },
            "estimate": {
                "tool": "uniswap",
                "toAmount": "1900000000",
                "toAmountMin": "1890500000",
                "fromAmount": "1000000000000000000",
                "gasCosts": [
                    {
                        "type": "SEND",
                        "amount": "30000000000000000",
                        "token": {
                            "address": "0x0000000000000000000000000000000000000000",
                            "chainId": 1,
                            "symbol": "ETH",
                            "decimals": 18,
                            "name": "Ethereum",
                        },
                        "estimate": "200000",
                        "limit": "250000",
                    }
                ],
                "executionDuration": 30,
            },
        },
        {
            "id": "step-2",
            "type": "cross",
            "tool": "stargate",
            "toolDetails": {
                "key": "stargate",
                "name": "Stargate",
                "logoURI": "https://example.com/stargate.svg",
            },
            "action": {
                "fromChainId": 1,
                "toChainId": 42161,
                "fromToken": {
                    "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "chainId": 1,
                    "symbol": "USDC",
                    "decimals": 6,
                    "name": "USD Coin",
                },
                "toToken": {
                    "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                    "chainId": 42161,
                    "symbol": "USDC",
                    "decimals": 6,
                    "name": "USD Coin",
                },
                "fromAmount": "1900000000",
                "slippage": 0.005,
                "fromAddress": "0x1234567890123456789012345678901234567890",
                "toAddress": "0x1234567890123456789012345678901234567890",
            },
            "estimate": {
                "tool": "stargate",
                "toAmount": "1850000000",
                "toAmountMin": "1840750000",
                "fromAmount": "1900000000",
                "gasCosts": [
                    {
                        "type": "SEND",
                        "amount": "20000000000000000",
                        "token": {
                            "address": "0x0000000000000000000000000000000000000000",
                            "chainId": 1,
                            "symbol": "ETH",
                            "decimals": 18,
                            "name": "Ethereum",
                        },
                        "estimate": "100000",
                        "limit": "150000",
                    }
                ],
                "executionDuration": 150,
            },
        },
    ],
    "transactionRequest": {
        "from": "0x1234567890123456789012345678901234567890",
        "to": "0xLifiDiamondContract12345678901234567890",
        "chainId": 1,
        "data": "0xabcdef1234567890",
        "value": "1000000000000000000",
        "gasPrice": "50000000000",
        "gasLimit": "400000",
    },
}

# Mock LI.FI status response (done)
MOCK_LIFI_STATUS_DONE = {
    "status": "DONE",
    "substatus": "COMPLETED",
    "substatusMessage": "Transfer completed successfully",
    "tool": "stargate",
    "transactionId": "lifi-quote-12345abcde",
    "sending": {
        "txHash": "0xabc123",
        "txLink": "https://etherscan.io/tx/0xabc123",
        "amount": "1000000000000000000",
        "token": {
            "address": "0x0000000000000000000000000000000000000000",
            "chainId": 1,
            "symbol": "ETH",
            "decimals": 18,
            "name": "Ethereum",
        },
        "chainId": 1,
    },
    "receiving": {
        "txHash": "0xdef456",
        "txLink": "https://arbiscan.io/tx/0xdef456",
        "amount": "1850000000",
        "token": {
            "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
            "chainId": 42161,
            "symbol": "USDC",
            "decimals": 6,
            "name": "USD Coin",
        },
        "chainId": 42161,
    },
    "lifiExplorerLink": "https://explorer.li.fi/tx/0xabc123",
}

# Mock LI.FI status response (pending)
MOCK_LIFI_STATUS_PENDING = {
    "status": "PENDING",
    "substatus": None,
    "tool": "stargate",
    "transactionId": "lifi-quote-12345abcde",
    "sending": {
        "txHash": "0xabc123",
        "txLink": "https://etherscan.io/tx/0xabc123",
        "amount": "1000000000000000000",
        "token": {
            "address": "0x0000000000000000000000000000000000000000",
            "chainId": 1,
            "symbol": "ETH",
            "decimals": 18,
            "name": "Ethereum",
        },
        "chainId": 1,
    },
}

# Mock LI.FI tokens response
MOCK_LIFI_TOKENS_RESPONSE = {
    "tokens": {
        "1": [
            {
                "address": "0x0000000000000000000000000000000000000000",
                "chainId": 1,
                "symbol": "ETH",
                "decimals": 18,
                "name": "Ethereum",
                "logoURI": "https://example.com/eth.png",
                "priceUSD": "2000.00",
            },
            {
                "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "chainId": 1,
                "symbol": "USDC",
                "decimals": 6,
                "name": "USD Coin",
                "logoURI": "https://example.com/usdc.png",
                "priceUSD": "1.00",
            },
        ],
        "42161": [
            {
                "address": "0x0000000000000000000000000000000000000000",
                "chainId": 42161,
                "symbol": "ETH",
                "decimals": 18,
                "name": "Ethereum",
                "logoURI": "https://example.com/eth.png",
                "priceUSD": "2000.00",
            },
            {
                "address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "chainId": 42161,
                "symbol": "USDC",
                "decimals": 6,
                "name": "USD Coin",
                "logoURI": "https://example.com/usdc.png",
                "priceUSD": "1.00",
            },
        ],
        "1151111081099710": [
            {
                "address": "11111111111111111111111111111111",
                "chainId": 1151111081099710,
                "symbol": "SOL",
                "decimals": 9,
                "name": "SOL",
                "logoURI": "https://example.com/sol.png",
                "priceUSD": "150.00",
            },
            {
                "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "chainId": 1151111081099710,
                "symbol": "USDC",
                "decimals": 6,
                "name": "USD Coin",
                "logoURI": "https://example.com/usdc.png",
                "priceUSD": "1.00",
            },
        ],
        "20000000000001": [
            {
                "address": "bitcoin",
                "chainId": 20000000000001,
                "symbol": "BTC",
                "decimals": 8,
                "name": "Bitcoin",
                "logoURI": "https://example.com/btc.png",
                "priceUSD": "60000.00",
            },
        ],
        "999999": [
            {
                "address": "0xUnknownChainToken",
                "chainId": 999999,
                "symbol": "UNK",
                "decimals": 18,
                "name": "Unknown",
                "logoURI": None,
                "priceUSD": None,
            },
        ],
    }
}

# Mock LI.FI error response
MOCK_LIFI_ERROR_RESPONSE = {
    "message": "No possible route found for this swap",
    "errors": [
        {"message": "Insufficient liquidity for this trade"},
    ],
}
