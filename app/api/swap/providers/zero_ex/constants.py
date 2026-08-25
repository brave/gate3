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
