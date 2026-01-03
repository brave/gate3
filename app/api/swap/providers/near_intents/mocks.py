from app.api.common.models import Chain, TokenInfo, TokenSource, TokenType

# Mock token data (raw API responses)
USDC_ON_SOLANA_TOKEN_DATA = {
    "assetId": "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
    "decimals": 6,
    "blockchain": "sol",
    "symbol": "USDC",
    "contractAddress": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}

BTC_TOKEN_DATA = {
    "assetId": "nep141:btc.omft.near",
    "decimals": 8,
    "blockchain": "btc",
    "symbol": "BTC",
    "contractAddress": None,
}

# Mock TokenInfo objects
USDC_ON_SOLANA_TOKEN_INFO = TokenInfo(
    coin=Chain.SOLANA.coin,
    chain_id=Chain.SOLANA.chain_id,
    address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    name="USDC",
    symbol="USDC",
    decimals=6,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
)

BTC_TOKEN_INFO = TokenInfo(
    coin=Chain.BITCOIN.coin,
    chain_id=Chain.BITCOIN.chain_id,
    address=None,
    name="BTC",
    symbol="BTC",
    decimals=8,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:btc.omft.near",
)

SOL_TOKEN_INFO = TokenInfo(
    coin=Chain.SOLANA.coin,
    chain_id=Chain.SOLANA.chain_id,
    address=None,  # Native SOL
    name="Solana",
    symbol="SOL",
    decimals=9,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:sol.omft.near",
)

ETH_TOKEN_INFO = TokenInfo(
    coin=Chain.ETHEREUM.coin,
    chain_id=Chain.ETHEREUM.chain_id,
    address=None,  # Native ETH
    name="Ethereum",
    symbol="ETH",
    decimals=18,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:eth.omft.near",
)

USDC_ON_ETHEREUM_TOKEN_INFO = TokenInfo(
    coin=Chain.ETHEREUM.coin,
    chain_id=Chain.ETHEREUM.chain_id,
    address="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC on Ethereum
    name="USD Coin",
    symbol="USDC",
    decimals=6,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.ERC20,
    near_intents_asset_id="nep141:eth-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.omft.near",
)

ZEC_TOKEN_INFO = TokenInfo(
    coin=Chain.ZCASH.coin,
    chain_id=Chain.ZCASH.chain_id,
    address=None,  # Native ZEC
    name="Zcash",
    symbol="ZEC",
    decimals=8,
    logo=None,
    sources=[TokenSource.NEAR_INTENTS],
    token_type=TokenType.UNKNOWN,
    near_intents_asset_id="nep141:zec.omft.near",
)

# Mock quote request/response data
MOCK_QUOTE_REQUEST = {
    "dry": True,
    "depositMode": "SIMPLE",
    "swapType": "EXACT_INPUT",
    "slippageTolerance": 50,
    "originAsset": "nep141:sol-5ce3bf3a31af18be40ba30f721101b4341690186.omft.near",
    "depositType": "ORIGIN_CHAIN",
    "destinationAsset": "nep141:btc.omft.near",
    "amount": "2037265",
    "refundTo": "8eekKfUAGSJbq3CdA2TmHb8tKuyzd5gtEas3MYAtXzrT",
    "refundType": "ORIGIN_CHAIN",
    "recipient": "bc1qpjqsdj3qvfl4hzfa49p28ns9xkpl73cyg9exzn",
    "recipientType": "DESTINATION_CHAIN",
    "deadline": "2025-12-11T13:48:50.883000Z",
    "referral": "brave",
    "quoteWaitingTimeMs": 0,
}

MOCK_FIRM_QUOTE = {
    "amountIn": "2037265",
    "amountInFormatted": "2.037265",
    "amountInUsd": "2.0373",
    "amountOut": "711",
    "amountOutFormatted": "0.00000711",
    "amountOutUsd": "0.6546",
    "minAmountOut": "707",
    "timeEstimate": 465,
    "depositAddress": "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE",
    "depositMemo": None,
    "deadline": "2025-12-11T13:48:50.883000Z",
}

MOCK_INDICATIVE_QUOTE = {
    **MOCK_FIRM_QUOTE,
    "depositAddress": None,
    "deadline": None,
}

# EXACT_OUTPUT mock quote request
MOCK_EXACT_OUTPUT_QUOTE_REQUEST = {
    **MOCK_QUOTE_REQUEST,
    "swapType": "EXACT_OUTPUT",
    "amount": "711",  # Desired output amount in base units
}

# EXACT_OUTPUT mock quote - has minAmountIn and maxAmountIn
MOCK_EXACT_OUTPUT_FIRM_QUOTE = {
    "amountIn": "2037265",  # Expected input amount
    "amountInFormatted": "2.037265",
    "amountInUsd": "2.0373",
    "minAmountIn": "2017265",  # Minimum input to proceed with swap
    "maxAmountIn": "2057265",  # Maximum input (excess refunded)
    "amountOut": "711",  # Exact output amount requested
    "amountOutFormatted": "0.00000711",
    "amountOutUsd": "0.6546",
    "minAmountOut": "711",  # For EXACT_OUTPUT, this equals amountOut
    "timeEstimate": 465,
    "depositAddress": "9RdSjLtfFJLvj6CAR4w7H7tUbv2kvwkkrYZuoojKDBkE",
    "depositMemo": None,
    "deadline": "2025-12-11T13:48:50.883000Z",
}

MOCK_EXACT_OUTPUT_INDICATIVE_QUOTE = {
    **MOCK_EXACT_OUTPUT_FIRM_QUOTE,
    "depositAddress": None,
    "deadline": None,
}
