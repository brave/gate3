import httpx

from app.api.common.models import Chain, Coin, TokenInfo, TokenType
from app.api.swap.cache import SupportedTokensCache
from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
    SwapType,
)
from app.api.swap.providers.base import BaseSwapProvider
from app.api.tokens.manager import TokenManager
from app.config import settings

from .constants import LIFI_BASE_URL, LIFI_CHAIN_TYPES
from .models import (
    LifiError,
    LifiQuoteRequest,
    LifiQuoteResponse,
    LifiStatusRequest,
    LifiStatusResponse,
    LifiTokensResponse,
)
from .transformations import from_lifi_quote_to_route, from_lifi_status
from .utils import (
    categorize_error,
    convert_lifi_slippage,
    convert_lifi_token_address,
    get_chain_from_lifi_chain_id,
    get_lifi_chain_id,
    get_lifi_token_address,
)


class LifiClient(BaseSwapProvider):
    """LI.FI API client for cross-chain swaps (EVM, Solana, Bitcoin)."""

    @property
    def provider_id(self) -> SwapProviderEnum:
        return SwapProviderEnum.LIFI

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
        self.base_url = LIFI_BASE_URL
        self.api_key = settings.LIFI_API_KEY
        self.token_manager = token_manager

    def _create_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-lifi-api-key"] = self.api_key

        return httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
        )

    async def get_supported_tokens(self) -> list[TokenInfo]:
        cached_tokens = await SupportedTokensCache.get(self.provider_id)
        if cached_tokens:
            return cached_tokens

        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/tokens",
                params={"chainTypes": LIFI_CHAIN_TYPES},
            )
            response.raise_for_status()
            data = response.json()

            lifi_response = LifiTokensResponse.model_validate(data)

            tokens = []
            for chain_id_str, token_list in lifi_response.tokens.items():
                chain = get_chain_from_lifi_chain_id(int(chain_id_str))
                if not chain:
                    continue

                for lifi_token in token_list:
                    address = convert_lifi_token_address(chain, lifi_token.address)

                    if chain.coin == Coin.ETH:
                        token_type = TokenType.ERC20
                    elif chain.coin == Coin.SOL:
                        token_type = TokenType.SPL_TOKEN
                    else:
                        token_type = TokenType.UNKNOWN

                    tokens.append(
                        TokenInfo(
                            coin=chain.coin,
                            chain_id=chain.chain_id,
                            address=address,
                            name=lifi_token.name,
                            symbol=lifi_token.symbol,
                            decimals=lifi_token.decimals,
                            logo=lifi_token.logo_uri,
                            sources=[],
                            token_type=token_type,
                        )
                    )

            await SupportedTokensCache.set(self.provider_id, tokens)
            return tokens

    async def has_support(self, request: SwapSupportRequest) -> bool:
        source_chain = request.source_chain
        dest_chain = request.destination_chain
        if not source_chain or not dest_chain:
            return False

        # BTC-as-source is not supported via LI.FI:
        # - Garden bridge doesn't support destination calls in single-tx mode
        # - Chainflip requires 2.5-5% slippage (far above typical user settings)
        # - LI.FI validates actual UTXOs on the sender address before returning
        #   a quote, which is incompatible with our UX (no wallet/account
        #   context at quote time)
        if source_chain == Chain.BITCOIN:
            return False

        source_lifi_id = get_lifi_chain_id(source_chain)
        dest_lifi_id = get_lifi_chain_id(dest_chain)

        return source_lifi_id is not None and dest_lifi_id is not None

    def _handle_error_response(self, response: httpx.Response) -> None:
        try:
            error_data = response.json()
            error = LifiError.model_validate(error_data)

            error_message = error.message
            if error.errors and len(error.errors) > 0:
                first_error = error.errors[0]
                error_message = first_error.get("message", error_message)

            kind = categorize_error(error_message)
            raise SwapError(message=error_message or "Unknown error", kind=kind)
        except SwapError:
            raise
        except Exception:
            raise SwapError(
                message=f"LI.FI API error: {response.status_code}",
                kind=SwapErrorKind.UNKNOWN,
            )

    async def _get_quote(
        self,
        request: SwapQuoteRequest,
    ) -> LifiQuoteResponse:
        if not await self.has_support(
            SwapSupportRequest(
                source_coin=request.source_coin,
                source_chain_id=request.source_chain_id,
                source_token_address=request.source_token_address,
                destination_coin=request.destination_coin,
                destination_chain_id=request.destination_chain_id,
                destination_token_address=request.destination_token_address,
                recipient=request.recipient,
            )
        ):
            raise SwapError(
                message="Unsupported network",
                kind=SwapErrorKind.UNSUPPORTED_NETWORK,
            )

        if (
            request.swap_type == SwapType.EXACT_OUTPUT
            and not self.has_exact_output_support
        ):
            raise SwapError(
                message="LI.FI does not support EXACT_OUTPUT swaps",
                kind=SwapErrorKind.INVALID_REQUEST,
            )

        quote_request = LifiQuoteRequest(
            from_chain=get_lifi_chain_id(request.source_chain),
            to_chain=get_lifi_chain_id(request.destination_chain),
            from_token=get_lifi_token_address(
                request.source_chain, request.source_token_address
            ),
            to_token=get_lifi_token_address(
                request.destination_chain, request.destination_token_address
            ),
            from_amount=request.amount,
            from_address=request.refund_to,
            to_address=request.recipient or request.refund_to,
            slippage=convert_lifi_slippage(request.slippage_percentage),
            order=request.route_priority.value,
            integrator="brave",
        )

        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/quote",
                params=quote_request.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            )

            if 200 <= response.status_code < 300:
                data = response.json()
                return LifiQuoteResponse.model_validate(data)

            self._handle_error_response(response)

    async def get_indicative_routes(
        self,
        request: SwapQuoteRequest,
    ) -> list[SwapRoute]:
        route = await self.get_firm_route(request)
        return [route]

    async def get_firm_route(self, request: SwapQuoteRequest) -> SwapRoute:
        lifi_response = await self._get_quote(request)
        return await from_lifi_quote_to_route(lifi_response, request)

    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        source_chain = Chain.get(request.source_coin.value, request.source_chain_id)
        dest_chain = Chain.get(
            request.destination_coin.value, request.destination_chain_id
        )

        source_chain_id = get_lifi_chain_id(source_chain) if source_chain else None
        dest_chain_id = get_lifi_chain_id(dest_chain) if dest_chain else None

        status_request = LifiStatusRequest(
            tx_hash=request.tx_hash,
            from_chain=source_chain_id,
            to_chain=dest_chain_id,
        )

        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/status",
                params=status_request.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            )

            if 200 <= response.status_code < 300:
                data = response.json()
                lifi_status = LifiStatusResponse.model_validate(data)
                return from_lifi_status(lifi_status, request)

            self._handle_error_response(response)
