import logging

import httpx

from app.api.common.models import TokenInfo
from app.config import settings

from ...cache import SupportedTokensCache
from ...models import (
    SwapProviderEnum,
    SwapQuote,
    SwapQuoteRequest,
    SwapStatusRequest,
    SwapStatusResponse,
    SwapSupportRequest,
)
from ..base import BaseSwapProvider
from .models import (
    NearIntentsError,
    NearIntentsQuoteResponse,
    NearIntentsStatusResponse,
    NearIntentsToken,
)
from .transformations import (
    from_near_intents_quote,
    from_near_intents_status,
    from_near_intents_token,
    to_near_intents_request,
)

logger = logging.getLogger(__name__)


class NearIntentsClient(BaseSwapProvider):
    """NEAR Intents 1Click API client"""

    @property
    def provider_id(self) -> SwapProviderEnum:
        return SwapProviderEnum.NEAR_INTENTS

    def __init__(self, token_manager=None):
        self.base_url = settings.NEAR_INTENTS_BASE_URL
        self.jwt_token = settings.NEAR_INTENTS_JWT
        self.token_manager = token_manager

    def _create_client(self) -> httpx.AsyncClient:
        headers = {}
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        return httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
        )

    async def get_supported_tokens(self) -> list[TokenInfo]:
        # Check cache first
        cached_tokens = await SupportedTokensCache.get(self.provider_id)
        if cached_tokens:
            return cached_tokens

        # Fetch from API
        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/v0/tokens")
            response.raise_for_status()
            data = response.json()

            tokens = []
            for token_data in data:
                token = NearIntentsToken.model_validate(token_data)
                if token_info := from_near_intents_token(token):
                    tokens.append(token_info)

            # Cache the results
            await SupportedTokensCache.set(self.provider_id, tokens)
            return tokens

    @staticmethod
    def _is_address_equal(a: str | None, b: str | None) -> bool:
        return (a or "").lower() == (b or "").lower()

    async def has_support(self, request: SwapSupportRequest) -> bool:
        if not request.source_chain or not request.destination_chain:
            return False

        if (
            request.source_chain.near_intents_id is None
            or request.destination_chain.near_intents_id is None
        ):
            return False

        # Get supported tokens
        supported_tokens = await self.get_supported_tokens()

        # Check if source token is supported
        source_supported = any(
            t.coin == request.source_coin
            and t.chain_id == request.source_chain_id
            and self._is_address_equal(t.address, request.source_token_address)
            for t in supported_tokens
        )

        # Check if destination token is supported
        destination_supported = any(
            t.coin == request.destination_coin
            and t.chain_id == request.destination_chain_id
            and self._is_address_equal(t.address, request.destination_token_address)
            for t in supported_tokens
        )

        return source_supported and destination_supported

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Raise ValueError with error message from NEAR Intents API"""
        error = NearIntentsError.model_validate(response.json())
        raise ValueError(error.message)

    async def _get_quote(self, request: SwapQuoteRequest, dry: bool) -> SwapQuote:
        """Internal method to get quote (indicative or firm)"""
        supported_tokens = await self.get_supported_tokens()
        near_request = to_near_intents_request(
            request, dry=dry, supported_tokens=supported_tokens
        )

        payload = near_request.model_dump(by_alias=True, mode="json")

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/quote",
                json=payload,
            )

            if 200 <= response.status_code < 300:
                data = response.json()
                near_response = NearIntentsQuoteResponse.model_validate(data)
                return from_near_intents_quote(near_response)

            self._handle_error_response(response)

    async def get_indicative_quote(self, request: SwapQuoteRequest) -> SwapQuote:
        return await self._get_quote(request, dry=True)

    async def get_firm_quote(self, request: SwapQuoteRequest) -> SwapQuote:
        return await self._get_quote(request, dry=False)

    async def post_submit_hook(self, request: SwapStatusRequest) -> None:
        """
        Post-submit hook that submits deposit transaction hash to NEAR Intents API.

        This allows the system to preemptively verify the deposit and can
        accelerate swap processing.

        Args:
            request: The swap status request containing tx_hash and deposit_address

        Raises:
            ValueError: If deposit transaction submission fails
            httpx.HTTPError: If API request fails
        """
        payload = {
            "txHash": request.tx_hash,
            "depositAddress": request.deposit_address,
        }

        if request.deposit_memo:
            payload["memo"] = request.deposit_memo

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/deposit/submit",
                json=payload,
            )

            if 200 <= response.status_code < 300:
                NearIntentsStatusResponse.model_validate(response.json())
                return

            self._handle_error_response(response)

    async def get_status(self, request: SwapStatusRequest) -> SwapStatusResponse:
        params = {"depositAddress": request.deposit_address}
        if request.deposit_memo:
            params["depositMemo"] = request.deposit_memo

        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/v0/status", params=params)

            if 200 <= response.status_code < 300:
                data = response.json()
                near_response = NearIntentsStatusResponse.model_validate(data)

                supported_tokens = await self.get_supported_tokens()
                return from_near_intents_status(near_response, supported_tokens)

            self._handle_error_response(response)
