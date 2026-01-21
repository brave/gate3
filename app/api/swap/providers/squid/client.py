import httpx

from app.api.common.models import Chain, Coin, TokenInfo
from app.api.swap.models import (
    SwapError,
    SwapErrorKind,
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
)
from app.api.swap.providers.base import BaseSwapProvider
from app.api.tokens.manager import TokenManager
from app.config import settings

from .models import (
    SquidError,
    SquidRouteRequest,
    SquidRouteResponse,
    SquidStatusRequest,
    SquidStatusResponse,
)
from .transformations import from_squid_route_to_route, from_squid_status
from .utils import (
    categorize_error,
    get_squid_chain_id_from_chain,
    get_squid_token_address,
)


class SquidClient(BaseSwapProvider):
    """Squid V2 API client for cross-chain swaps (EVM, Bitcoin, Solana)."""

    @property
    def provider_id(self) -> SwapProviderEnum:
        return SwapProviderEnum.SQUID

    @property
    def has_post_submit_hook(self) -> bool:
        return False

    @property
    def requires_token_allowance(self) -> bool:
        return True

    @property
    def requires_firm_route(self) -> bool:
        """Squid provides transaction in route response, so firm route is not required."""
        return False

    @property
    def has_auto_slippage_support(self) -> bool:
        return True

    def __init__(self, token_manager: TokenManager):
        self.base_url = "https://v2.api.squidrouter.com"
        self.integrator_id = settings.SQUID_INTEGRATOR_ID
        self.token_manager = token_manager

    def _create_client(self) -> httpx.AsyncClient:
        headers = {"Content-Type": "application/json"}
        if self.integrator_id:
            headers["x-integrator-id"] = self.integrator_id

        return httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
        )

    async def get_supported_tokens(self) -> list[TokenInfo]:
        raise NotImplementedError

    async def has_support(self, request: SwapSupportRequest) -> bool:
        """Check if Squid supports the requested swap.

        Squid supports swaps from EVM chains to EVM, Bitcoin, and Solana chains.

        Args:
            request: The swap support request

        Returns:
            True if Squid supports this swap, False otherwise
        """
        # Source must be an EVM chain
        if request.source_coin != Coin.ETH:
            return False

        # Destination can be EVM, Bitcoin, or Solana
        if request.destination_coin not in {Coin.ETH, Coin.BTC, Coin.SOL}:
            return False

        # Get chain objects and validate they are resolvable
        source_chain = request.source_chain
        dest_chain = request.destination_chain
        if not source_chain or not dest_chain:
            return False

        # Validate both chains are supported by Squid
        source_squid_id = get_squid_chain_id_from_chain(source_chain)
        dest_squid_id = get_squid_chain_id_from_chain(dest_chain)

        return source_squid_id is not None and dest_squid_id is not None

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Raise SwapError with categorized error message from Squid API."""
        try:
            error_data = response.json()
            error = SquidError.model_validate(error_data)

            # Extract error message from various fields
            error_message = error.message or error.error
            if error.errors and len(error.errors) > 0:
                first_error = error.errors[0]
                error_message = first_error.get("message", error_message)

            kind = categorize_error(error_message)
            raise SwapError(message=error_message or "Unknown error", kind=kind)
        except SwapError:
            raise
        except Exception:
            raise SwapError(
                message=f"Squid API error: {response.status_code}",
                kind=SwapErrorKind.UNKNOWN,
            )

    async def _get_route(
        self,
        request: SwapQuoteRequest,
    ) -> SquidRouteResponse:
        """Get route from Squid V2 API.

        Args:
            request: The swap quote request

        Returns:
            SquidRouteResponse with route and transaction data

        Raises:
            SwapError: If the API request fails
        """
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
                message="Unsupported chain",
                kind=SwapErrorKind.UNKNOWN,
            )

        route_request = SquidRouteRequest(
            from_chain=get_squid_chain_id_from_chain(request.source_chain),
            from_token=get_squid_token_address(
                request.source_chain, request.source_token_address
            ),
            from_amount=request.amount,
            to_chain=get_squid_chain_id_from_chain(request.destination_chain),
            to_token=get_squid_token_address(
                request.destination_chain, request.destination_token_address
            ),
            to_address=request.recipient or request.refund_to,
            slippage=(
                float(request.slippage_percentage)
                if request.slippage_percentage
                else None
            ),
            from_address=request.refund_to,
        )

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v2/route",
                json=route_request.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            )

            if 200 <= response.status_code < 300:
                data = response.json()
                return SquidRouteResponse.model_validate(data)

            self._handle_error_response(response)
            raise SwapError(
                message="Unhandled Squid API error",
                kind=SwapErrorKind.UNKNOWN,
            )

    async def get_indicative_routes(
        self,
        request: SwapQuoteRequest,
    ) -> list[SwapRoute]:
        """Get indicative routes from Squid.

        Squid provides transaction data in the route response, so we use
        get_firm_route for both indicative and firm quotes.

        Args:
            request: The swap quote request

        Returns:
            List of SwapRoute (Squid typically returns one route)
        """
        route = await self.get_firm_route(request)
        return [route]

    async def get_firm_route(self, request: SwapQuoteRequest) -> SwapRoute:
        """Get firm route from Squid.

        Squid provides the transaction in the route response.

        Args:
            request: The swap quote request

        Returns:
            SwapRoute with transaction parameters
        """
        squid_response = await self._get_route(request)

        return await from_squid_route_to_route(
            squid_response,
            request,
            self.token_manager,
        )

    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        """Get swap status from Squid.

        Args:
            request: The swap status request containing tx_hash and route id

        Returns:
            SwapStatusResponse with current status

        Raises:
            SwapError: If the API request fails
        """
        # Get chain objects from request
        source_chain = Chain.get(request.source_coin.value, request.source_chain_id)
        dest_chain = Chain.get(
            request.destination_coin.value, request.destination_chain_id
        )

        if not source_chain or not dest_chain:
            raise SwapError(
                message="Unsupported chain",
                kind=SwapErrorKind.UNKNOWN,
            )

        source_chain_id = get_squid_chain_id_from_chain(source_chain)
        dest_chain_id = get_squid_chain_id_from_chain(dest_chain)

        # Build request using Pydantic model
        status_request = SquidStatusRequest(
            transaction_id=request.tx_hash,
            from_chain_id=source_chain_id,
            to_chain_id=dest_chain_id,
            request_id=request.route_id,
        )

        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/v2/status",
                params=status_request.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            )

            if 200 <= response.status_code < 300:
                data = response.json()
                squid_status = SquidStatusResponse.model_validate(data)
                return from_squid_status(squid_status, request)

            self._handle_error_response(response)
            raise SwapError(
                message="Unhandled Squid API error",
                kind=SwapErrorKind.UNKNOWN,
            )

    async def post_submit_hook(self, request: SwapStatusRequest) -> None:
        """Post-submit hook for Squid.

        Squid does not require a post-submit hook, so this is a no-op.

        Args:
            request: The swap status request
        """
        pass
