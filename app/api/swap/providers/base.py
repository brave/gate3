from abc import ABC, abstractmethod

from ..models import (
    SwapProviderEnum,
    SwapQuoteRequest,
    SwapRoute,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
    TokenInfo,
)


class BaseSwapProvider(ABC):
    """Abstract base class for swap providers"""

    @property
    @abstractmethod
    def provider_id(self) -> SwapProviderEnum:
        """Get the SwapProviderEnum value that identifies this provider.

        Returns:
            SwapProviderEnum value for this provider implementation

        """

    @property
    def has_post_submit_hook(self) -> bool:
        """Whether client must call post-submit hook after deposit transaction.

        Returns:
            True if post-submit hook is required, False otherwise

        """
        return False

    @property
    def requires_token_allowance(self) -> bool:
        """Whether client must check/approve ERC20 token allowance before swap (EVM only).

        Returns:
            True if allowance check is required, False otherwise

        """
        return False

    @property
    def requires_firm_route(self) -> bool:
        """Whether client must fetch a firm route before executing the swap.

        Some providers include all necessary details in the indicative route,
        making a separate firm route request unnecessary.

        Returns:
            True if firm route is required, False otherwise

        """
        return True

    @abstractmethod
    async def get_supported_tokens(self) -> list[TokenInfo]:
        """Get list of tokens supported by this provider.

        Returns:
            List of TokenInfo with supported tokens

        """

    @abstractmethod
    async def has_support(self, request: SwapSupportRequest) -> bool:
        """Check if provider supports the requested swap parameters.

        Args:
            request: The swap support request

        Returns:
            True if provider supports this swap, False otherwise

        """

    @abstractmethod
    async def get_indicative_routes(self, request: SwapQuoteRequest) -> list[SwapRoute]:
        """Get indicative routes for a swap.
        This is a dry run to preview swap parameters.

        Args:
            request: The swap quote request

        Returns:
            List of SwapRoute options

        Raises:
            ValueError: If swap is not supported or parameters are invalid
            httpx.HTTPError: If API request fails

        """

    @abstractmethod
    async def get_firm_route(self, request: SwapQuoteRequest) -> SwapRoute:
        """Get a firm route for a swap.
        User must send funds to the deposit address to initiate the swap.

        Args:
            request: The swap quote request

        Returns:
            SwapRoute with deposit address, deadline, and transaction params

        Raises:
            ValueError: If swap is not supported or parameters are invalid
            httpx.HTTPError: If API request fails

        """

    @abstractmethod
    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        """Get the current status of a swap.

        Args:
            request: The swap status request

        Returns:
            SwapStatusResponse with current status and details

        Raises:
            ValueError: If swap status request is not supported
            httpx.HTTPError: If API request fails

        """

    @abstractmethod
    async def post_submit_hook(self, request: SwapStatusRequest) -> None:
        """Post-submit hook called after a deposit transaction is submitted.

        This hook can be used by providers to perform provider-specific actions
        after a deposit transaction has been submitted. The exact behavior and
        purpose of this hook is implementation-specific to each provider.

        Args:
            request: The swap status request containing tx_hash and deposit_address

        Raises:
            ValueError: If the hook operation fails
            httpx.HTTPError: If API request fails

        """
