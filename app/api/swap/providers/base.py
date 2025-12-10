from abc import ABC, abstractmethod

from ..models import (
    SwapQuoteRequest,
    SwapQuoteResponse,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
    TokenInfo,
)


class SwapProvider(ABC):
    """Abstract base class for swap providers"""

    @abstractmethod
    async def get_supported_tokens(self) -> list[TokenInfo]:
        """
        Get list of tokens supported by this provider.

        Returns:
            List of TokenInfo with supported tokens
        """
        pass

    @abstractmethod
    async def has_support(self, request: SwapSupportRequest) -> bool:
        """
        Check if provider supports the requested swap parameters.

        Args:
            request: The swap support request

        Returns:
            True if provider supports this swap, False otherwise
        """
        pass

    @abstractmethod
    async def get_indicative_quote(
        self, request: SwapQuoteRequest
    ) -> SwapQuoteResponse:
        """
        Get an indicative quote without creating a deposit address.
        This is a dry run to preview swap parameters.

        Args:
            request: The swap quote request

        Returns:
            SwapQuoteResponse without deposit address

        Raises:
            ValueError: If swap is not supported or parameters are invalid
            httpx.HTTPError: If API request fails
        """
        pass

    @abstractmethod
    async def get_firm_quote(self, request: SwapQuoteRequest) -> SwapQuoteResponse:
        """
        Get a firm quote with a deposit address.
        User must send funds to this address to initiate the swap.

        Args:
            request: The swap quote request

        Returns:
            SwapQuoteResponse with deposit address and deadline

        Raises:
            ValueError: If swap is not supported or parameters are invalid
            httpx.HTTPError: If API request fails
        """
        pass

    @abstractmethod
    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        """
        Get the current status of a swap.

        Args:
            request: The swap status request

        Returns:
            SwapStatusResponse with current status and details

        Raises:
            ValueError: If swap status request is not supported
            httpx.HTTPError: If API request fails
        """
        pass

    @abstractmethod
    async def post_submit_hook(self, request: SwapStatusRequest) -> None:
        """
        Post-submit hook called after a deposit transaction is submitted.

        This hook can be used by providers to perform provider-specific actions
        after a deposit transaction has been submitted. The exact behavior and
        purpose of this hook is implementation-specific to each provider.

        Args:
            request: The swap status request containing tx_hash and deposit_address

        Raises:
            ValueError: If the hook operation fails
            httpx.HTTPError: If API request fails
        """
        pass
