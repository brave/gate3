from app.api.common.models import Chain

ZERO_EX_BASE_URL = "https://api.0x.org"
ZERO_EX_API_VERSION = "v2"

# 0x native token sentinel (EIP-7528 convention)
ZERO_EX_NATIVE_TOKEN_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

ZERO_EX_SUPPORTED_CHAINS: tuple[Chain, ...] = (
    Chain.ETHEREUM,
    Chain.ARBITRUM,
    Chain.AVALANCHE,
    Chain.BASE,
    Chain.BNB_CHAIN,
    Chain.OPTIMISM,
    Chain.POLYGON,
)

ZERO_EX_EXPLORER_URLS: dict[str, str] = {
    Chain.ETHEREUM.chain_id: "https://etherscan.io",
    Chain.ARBITRUM.chain_id: "https://arbiscan.io",
    Chain.AVALANCHE.chain_id: "https://snowtrace.io",
    Chain.BASE.chain_id: "https://basescan.org",
    Chain.BNB_CHAIN.chain_id: "https://bscscan.com",
    Chain.OPTIMISM.chain_id: "https://optimistic.etherscan.io",
    Chain.POLYGON.chain_id: "https://polygonscan.com",
}
