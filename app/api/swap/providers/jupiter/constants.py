from ...models import SwapTool

# Jupiter tool info for route steps
JUPITER_TOOL = SwapTool(
    name="Jupiter",
    logo="https://static1.tokenterminal.com/jupiter/logo.png",
)

TOOLS = [
    SwapTool(
        name="HumidiFi",
        logo="https://static1.tokenterminal.com/humidifi/logo.png",
    ),
    JUPITER_TOOL,
    SwapTool(
        name="Meteora DLMM",  # matches: "Meteora DLMM", "Meteora"
        logo="https://static1.tokenterminal.com/meteora/products/meteoradlmm/logo.png",
    ),
    SwapTool(
        name="OKX DEX Router",
        logo="https://static1.tokenterminal.com/okx/logo.png",
    ),
    SwapTool(
        name="PancakeSwap",
        logo="https://static1.tokenterminal.com/pancakeswap/logo.png",
    ),
    SwapTool(
        name="Pump.fun Amm",
        logo="https://static1.tokenterminal.com/pumpfun/products/pumpfun/logo.png",
    ),
    SwapTool(
        name="Raydium CLMM",
        logo="https://static1.tokenterminal.com/raydium/products/raydiumclmm/logo.png",
    ),
    SwapTool(
        name="Stabble Stable Swap",
        logo="https://static1.tokenterminal.com/stabble/logo.png",
    ),
    SwapTool(
        name="Whirlpools",  # matches: "Whirlpool", "Whirlpools"
        logo="https://static1.tokenterminal.com/orca/products/whirlpools/logo.png",
    ),
]

# Solana native token mint address
SOL_MINT = "So11111111111111111111111111111111111111112"
