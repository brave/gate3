from datetime import timedelta

from app.api.common.models import Chain

from ...models import SwapTool

# NEAR Intents tool info for route steps
NEAR_INTENTS_TOOL = SwapTool(
    name="NEAR Intents",
    logo="https://static1.tokenterminal.com/near/products/nearintents/logo.png",
)

# Gas/compute unit estimates for different transaction types
# These are conservative estimates - actual values may vary
EVM_GAS_LIMIT_NATIVE_TRANSFER = 21_000
EVM_GAS_LIMIT_ERC20_TRANSFER = 65_000

SOLANA_BASE_FEE_LAMPORTS = 5_000
SOLANA_LAMPORTS_PER_SOL = 1_000_000_000
SOLANA_COMPUTE_UNIT_PRICE_LAMPORTS = 1 / 1_000_000  # 1 micro-lamport per compute unit
SOLANA_COMPUTE_UNIT_LIMIT = 200_000

# How long NEAR Intents waits for the deposit before refunding it. Slow chains
# need longer, or a deposit can confirm after the deadline and get refunded.
QUOTE_DEADLINE = timedelta(minutes=10)
QUOTE_DEADLINE_BY_SOURCE_CHAIN = {
    Chain.BITCOIN: timedelta(minutes=60),
    Chain.ZCASH: timedelta(minutes=30),
}
