from app.api.common.models import Chain, TokenInfo, TokenSource, TokenType

# Mock token data
SOL_TOKEN_INFO = TokenInfo(
    coin=Chain.SOLANA.coin,
    chain_id=Chain.SOLANA.chain_id,
    address=None,  # Native SOL
    name="Solana",
    symbol="SOL",
    decimals=9,
    logo=None,
    sources=[TokenSource.JUPITER_VERIFIED],
    token_type=TokenType.SPL_TOKEN,
)

USDC_ON_SOLANA_TOKEN_INFO = TokenInfo(
    coin=Chain.SOLANA.coin,
    chain_id=Chain.SOLANA.chain_id,
    address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    name="USD Coin",
    symbol="USDC",
    decimals=6,
    logo=None,
    sources=[TokenSource.JUPITER_VERIFIED],
    token_type=TokenType.SPL_TOKEN,
)

# Mock Jupiter order response (EXACT_INPUT)
MOCK_JUPITER_ORDER_RESPONSE = {
    "inAmount": "100000000",
    "outAmount": "13882709",
    "otherAmountThreshold": "13811907",
    "swapMode": "ExactIn",
    "slippageBps": 51,
    "priceImpact": "-0.00011902847845983851",
    "routePlan": [
        {
            "percent": 100,
            "bps": 10000,
            "usdValue": 13.882608757455545,
            "swapInfo": {
                "ammKey": "3QYYvFWgSuGK8bbxMSAYkCqE8QfSuFtByagnZAuekia2",
                "label": "HumidiFi",
                "inputMint": "So11111111111111111111111111111111111111112",
                "outputMint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "inAmount": "100000000",
                "outAmount": "13889289",
                "marketIncurredSlippageBpsF64": "4.239272860805456",
            },
        },
        {
            "percent": 100,
            "bps": 10000,
            "usdValue": 13.882608757455545,
            "swapInfo": {
                "ammKey": "CNC5TaeNQEoSPfQKZ7GgfM4R8WYAJRKRSHFCHkf2H7ko",
                "label": "Aquifer",
                "inputMint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
                "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "inAmount": "13889289",
                "outAmount": "13882709",
                "marketIncurredSlippageBpsF64": "0",
            },
        },
    ],
    "feeMint": "So11111111111111111111111111111111111111112",
    "feeBps": 2,
    "taker": "11111111111111111111111111111111",
    "gasless": False,
    "signatureFeeLamports": 0,
    "signatureFeePayer": None,
    "prioritizationFeeLamports": 0,
    "prioritizationFeePayer": None,
    "transaction": "AQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAQABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fICEiIyQlJic=",
    "errorCode": None,
    "errorMessage": None,
    "inputMint": "So11111111111111111111111111111111111111112",
    "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "router": "iris",
    "requestId": "019b9505-9f12-7071-a0eb-763a5f5c4b70",
    "inUsdValue": 13.884261379962142,
    "outUsdValue": 13.882608757455547,
    "swapUsdValue": 13.882608757455547,
    "mode": "ultra",
    "error": None,
    "totalTime": 363,
    "expireAt": "2025-01-07T12:00:00Z",
}

# Mock Jupiter execute response
MOCK_JUPITER_EXECUTE_RESPONSE = {
    "signature": "5VERv8NMvzbJMEkV8xnrLkEaWRt6sp5Yg8ZvNugvE77B4HM4ofM4X2s5N2fGm3C4",
    "error": None,
    "requestId": "019b9505-9f12-7071-a0eb-763a5f5c4b70",
}
