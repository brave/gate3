import asyncio

import httpx

from app.api.common.evm.tx_status import (
    EvmTxReceiptStatus,
    get_evm_tx_receipt_status,
)
from app.api.common.models import Chain, Coin, TokenInfo
from app.api.common.utils import is_address_equal
from app.api.swap.cache import SupportedTokensCache
from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapStatus,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
    SwapType,
)
from app.api.swap.providers.base import BaseSwapProvider
from app.api.tokens.manager import TokenManager
from app.config import settings
from app.core.http import create_http_client

from .constants import (
    ZERO_EX_API_VERSION,
    ZERO_EX_BASE_URL,
    ZERO_EX_EXPLORER_URLS,
    ZERO_EX_SUPPORTED_CHAINS,
)
from .models import ZeroExError, ZeroExQuoteResponse
from .transformations import from_zero_ex_quote_to_route
from .utils import (
    categorize_error,
    convert_slippage_to_bps,
    from_zero_ex_token_address,
    get_zero_ex_chain_id,
    get_zero_ex_token_address,
)

_RECEIPT_STATUS_TO_SWAP_STATUS: dict[EvmTxReceiptStatus, SwapStatus] = {
    EvmTxReceiptStatus.SUCCESS: SwapStatus.SUCCESS,
    EvmTxReceiptStatus.FAILED: SwapStatus.FAILED,
    EvmTxReceiptStatus.PENDING: SwapStatus.PENDING,
}


class ZeroExClient(BaseSwapProvider):
    """0x Protocol Swap API v2 client (single-chain EVM swaps)."""

    @property
    def provider_id(self) -> SwapProviderEnum:
        return SwapProviderEnum.ZERO_EX

    @property
    def requires_token_allowance(self) -> bool:
        return True

    @property
    def requires_firm_route(self) -> bool:
        return False

    @property
    def has_auto_slippage_support(self) -> bool:
        return False

    @property
    def has_exact_output_support(self) -> bool:
        return False

    def __init__(self, token_manager: TokenManager):
        self.base_url = ZERO_EX_BASE_URL
        self.api_key = settings.ZERO_EX_API_KEY
        self.token_manager = token_manager

    def _create_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {"0x-version": ZERO_EX_API_VERSION}
        if self.api_key:
            headers["0x-api-key"] = self.api_key

        return create_http_client(
            timeout=10.0,
            headers=headers,
        )

    async def get_supported_tokens(self) -> list[TokenInfo]:
        cached_tokens = await SupportedTokensCache.get(self.provider_id)
        if cached_tokens:
            return cached_tokens

        per_chain = await asyncio.gather(
            *(
                TokenManager.list_tokens(Coin.ETH, chain.chain_id)
                for chain in ZERO_EX_SUPPORTED_CHAINS
            )
        )
        tokens: list[TokenInfo] = [t for chunk in per_chain for t in chunk]

        await SupportedTokensCache.set(self.provider_id, tokens)
        return tokens

    async def has_support(self, request: SwapSupportRequest) -> bool:
        source_chain = request.source_chain
        dest_chain = request.destination_chain

        if not source_chain or not dest_chain:
            return False

        if source_chain.coin != Coin.ETH or dest_chain.coin != Coin.ETH:
            return False

        if source_chain != dest_chain:
            return False

        if source_chain not in ZERO_EX_SUPPORTED_CHAINS:
            return False

        src = from_zero_ex_token_address(request.source_token_address)
        dst = from_zero_ex_token_address(request.destination_token_address)
        if is_address_equal(src, dst):
            return False

        return True

    def _handle_error_response(self, response: httpx.Response) -> None:
        try:
            error_data = response.json()
            error = ZeroExError.model_validate(error_data)
        except Exception:
            raise SwapError(
                message=f"0x API error (status {response.status_code})",
                kind=categorize_error(
                    ZeroExError(name=None, message=""), response.status_code
                ),
            )

        kind = categorize_error(error, response.status_code)
        raise SwapError(message=error.message or "0x API error", kind=kind)

    async def _get_quote(self, request: SwapQuoteRequest) -> ZeroExQuoteResponse:
        if request.swap_type == SwapType.EXACT_OUTPUT:
            raise SwapError(
                message="0x does not support EXACT_OUTPUT swaps",
                kind=SwapErrorKind.INVALID_REQUEST,
            )

        if request.recipient and not is_address_equal(
            request.recipient, request.refund_to
        ):
            raise SwapError(
                message="0x does not support a recipient different from the taker",
                kind=SwapErrorKind.INVALID_REQUEST,
            )

        chain_id = get_zero_ex_chain_id(request.source_chain)
        if chain_id is None:
            raise SwapError(
                message="Unsupported chain for 0x",
                kind=SwapErrorKind.UNSUPPORTED_NETWORK,
            )

        params: dict[str, str | int] = {
            "chainId": chain_id,
            "sellToken": get_zero_ex_token_address(request.source_token_address),
            "buyToken": get_zero_ex_token_address(request.destination_token_address),
            "sellAmount": request.amount,
            "taker": request.refund_to,
        }

        slippage_bps = convert_slippage_to_bps(request.slippage_percentage)
        if slippage_bps is None and request.slippage_percentage is not None:
            raise SwapError(
                message=f"Invalid slippagePercentage: {request.slippage_percentage!r}",
                kind=SwapErrorKind.INVALID_REQUEST,
            )
        if slippage_bps is not None:
            params["slippageBps"] = slippage_bps

        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/swap/allowance-holder/quote",
                params=params,
            )

            if 200 <= response.status_code < 300:
                data = response.json()
                if data.get("liquidityAvailable") is False:
                    raise SwapError(
                        message="No liquidity available for this swap",
                        kind=SwapErrorKind.INSUFFICIENT_LIQUIDITY,
                    )
                return ZeroExQuoteResponse.model_validate(data)

            self._handle_error_response(response)

    async def get_indicative_routes(self, request: SwapQuoteRequest) -> list[SwapRoute]:
        route = await self.get_firm_route(request)
        return [route]

    async def get_firm_route(self, request: SwapQuoteRequest) -> SwapRoute:
        zero_ex_response = await self._get_quote(request)
        return await from_zero_ex_quote_to_route(
            zero_ex_response, request, self.token_manager
        )

    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        chain = Chain.get(request.source_coin.value, request.source_chain_id)

        status = SwapStatus.PENDING
        explorer_url: str | None = None
        if chain is not None:
            if chain in ZERO_EX_SUPPORTED_CHAINS:
                receipt_status = await get_evm_tx_receipt_status(chain, request.tx_hash)
                status = _RECEIPT_STATUS_TO_SWAP_STATUS[receipt_status]
            explorer_base = ZERO_EX_EXPLORER_URLS.get(chain.chain_id)
            if explorer_base:
                explorer_url = f"{explorer_base}/tx/{request.tx_hash}"

        return SwapStatusResponse(
            status=status,
            internal_status=None,
            explorer_url=explorer_url,
        )
