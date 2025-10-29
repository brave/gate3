from abc import ABC, abstractmethod

from ..models import (
    SubmitDepositRequest,
    SwapQuoteRequest,
    SwapQuoteResponse,
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
    async def get_swap_status(
        self, deposit_address: str, deposit_memo: str | None = None
    ) -> SwapStatusResponse:
        """
        Get the current status of a swap.

        Args:
            deposit_address: The deposit address from the firm quote
            deposit_memo: Optional memo (required for some chains like Stellar)

        Returns:
            SwapStatusResponse with current status and details

        Raises:
            ValueError: If deposit address not found
            httpx.HTTPError: If API request fails
        """
        pass

    @abstractmethod
    async def submit_deposit_tx(
        self, request: SubmitDepositRequest
    ) -> SwapStatusResponse:
        """
        Optionally submit deposit transaction hash to speed up processing.

        Args:
            request: Deposit submission request with tx hash and deposit address

        Returns:
            SwapStatusResponse with current status

        Raises:
            ValueError: If deposit address not found or tx invalid
            httpx.HTTPError: If API request fails
        """
        pass
