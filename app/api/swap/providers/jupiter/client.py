import httpx

from app.api.common.models import Chain, TokenInfo
from app.api.common.utils import is_address_equal
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

from .constants import SOL_MINT
from .models import (
    JupiterError,
    JupiterOrderRequest,
    JupiterOrderResponse,
    JupiterSwapMode,
)
from .transformations import from_jupiter_order_to_route
from .utils import categorize_error


class JupiterClient(BaseSwapProvider):
    """Jupiter Ultra V3 API client for Solana swaps"""

    @property
    def provider_id(self) -> SwapProviderEnum:
        return SwapProviderEnum.JUPITER

    @property
    def has_post_submit_hook(self) -> bool:
        return False

    @property
    def requires_token_allowance(self) -> bool:
        return False

    @property
    def requires_firm_route(self) -> bool:
        """Jupiter provides transaction in order response, so firm route is not required."""
        return False

    @property
    def has_auto_slippage_support(self) -> bool:
        return True

    def __init__(self, token_manager: TokenManager):
        self.base_url = "https://api.jup.ag"
        self.api_key = settings.JUPITER_API_KEY
        self.token_manager = token_manager

    def _create_client(self) -> httpx.AsyncClient:
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        return httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
        )

    async def get_supported_tokens(self) -> list[TokenInfo]:
        raise NotImplementedError

    async def has_support(self, request: SwapSupportRequest) -> bool:
        """Check if Jupiter supports the requested swap.

        Jupiter only supports Solana swaps (same chain).

        Args:
            request: The swap support request

        Returns:
            True if Jupiter supports this swap, False otherwise
        """
        if not request.source_chain or not request.destination_chain:
            return False
        return request.source_chain == request.destination_chain == Chain.SOLANA

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Raise SwapError with categorized error message from Jupiter API.

        Jupiter errors are typically in the format: {"error": "Failed to get quotes"}
        """
        try:
            error_data = response.json()
            error = JupiterError.model_validate(error_data)
            error_message = error.error
            kind = categorize_error(error_message)
            raise SwapError(message=error_message, kind=kind)
        except SwapError:
            # Re-raise SwapError as-is
            raise
        except Exception:
            # If we can't parse the error, raise a generic error
            raise SwapError(
                message=f"Jupiter API error: {response.status_code}",
                kind=SwapErrorKind.UNKNOWN,
            )

    async def _get_order(
        self,
        request: SwapQuoteRequest,
    ) -> JupiterOrderResponse:
        """Get order from Jupiter Ultra V3 API.

        Args:
            request: The swap quote request

        Returns:
            JupiterOrderResponse with quote and transaction

        Raises:
            SwapError: If the API request fails
        """
        order_request = JupiterOrderRequest(
            input_mint=request.source_token_address or SOL_MINT,
            output_mint=request.destination_token_address or SOL_MINT,
            amount=request.amount,
            taker=request.refund_to,  # Jupiter uses wallet address as the taker
            swap_mode=(
                JupiterSwapMode.EXACT_IN
                if request.swap_type == SwapType.EXACT_INPUT
                else JupiterSwapMode.EXACT_OUT
            ),
            receiver=(
                request.recipient
                if not is_address_equal(request.recipient, request.refund_to)
                else None
            ),
        )

        # Convert to query parameters (exclude None values)
        params = order_request.model_dump(by_alias=True, mode="json", exclude_none=True)

        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/ultra/v1/order", params=params
            )

            if 200 <= response.status_code < 300:
                data = response.json()

                # Raise error if the response is explicitly an error
                # Responses with a valid quote but with an "error" key are
                # considered warnings which should be handled by the clients.
                if data.get("error") and not data.get("inAmount"):
                    error_message = data.get("error") or "Unknown Jupiter API error"
                    kind = categorize_error(error_message)
                    raise SwapError(message=error_message, kind=kind)

                return JupiterOrderResponse.model_validate(data)

            self._handle_error_response(response)
            # _handle_error_response is expected to always raise SwapError,
            # but add an explicit raise to make the control flow clear.
            raise SwapError(
                message="Unhandled Jupiter API error", kind=SwapErrorKind.UNKNOWN
            )

    async def get_indicative_routes(
        self,
        request: SwapQuoteRequest,
    ) -> list[SwapRoute]:
        """Get indicative routes from Jupiter.

        For Jupiter, we use the order endpoint which returns both quote and transaction.
        We can use this for indicative quotes as well.

        Args:
            request: The swap quote request

        Returns:
            List of SwapRoute (Jupiter typically returns one route)
        """
        route = await self.get_firm_route(request)
        return [route]

    async def get_firm_route(self, request: SwapQuoteRequest) -> SwapRoute:
        """Get firm route from Jupiter.

        Jupiter provides the transaction in the order response, so this is
        similar to indicative but marks it as firm.

        Args:
            request: The swap quote request

        Returns:
            SwapRoute with transaction parameters
        """
        jupiter_response = await self._get_order(request)

        return await from_jupiter_order_to_route(
            jupiter_response,
            request,
            self.token_manager,
        )

    async def post_submit_hook(self, request: SwapStatusRequest) -> None:
        """Post-submit hook for Jupiter.

        Jupiter does not require a post-submit hook, so this is a no-op.

        Args:
            request: The swap status request
        """
        # Jupiter doesn't require post-submit hook
        pass

    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        """Get swap status from Jupiter.

        Note: Jupiter Ultra V3 doesn't have a dedicated status endpoint.
        We would need to check the transaction on-chain.

        Args:
            request: The swap status request

        Returns:
            SwapStatusResponse with inferred status
        """
        raise NotImplementedError
