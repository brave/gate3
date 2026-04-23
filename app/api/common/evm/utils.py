"""Shared EVM utilities: chain validation and Alchemy RPC URL resolution."""

from app.config import settings

from ..models import Chain, Coin

ALCHEMY_RPC_URL_TEMPLATE = "https://{network}.g.alchemy.com/v2/{api_key}"


class NotEvmChainError(ValueError):
    """Raised when a non-EVM chain is passed to an EVM-only function."""

    def __init__(self, chain: Chain):
        self.chain = chain
        super().__init__(f"Chain {chain} is not an EVM chain (coin={chain.coin})")


def validate_evm_chain(chain: Chain) -> None:
    if chain.coin != Coin.ETH:
        raise NotEvmChainError(chain)


def get_alchemy_rpc_url(chain: Chain) -> str | None:
    validate_evm_chain(chain)

    if not settings.ALCHEMY_API_KEY:
        return None

    return ALCHEMY_RPC_URL_TEMPLATE.format(
        network=chain.alchemy_id,
        api_key=settings.ALCHEMY_API_KEY,
    )
