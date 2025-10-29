import httpx

from app.api.common.models import TokenInfo
from app.config import settings

from ...cache import SupportedTokensCache
from ...models import (
    SubmitDepositRequest,
    SwapQuoteRequest,
    SwapQuoteResponse,
    SwapStatusResponse,
    SwapSupportRequest,
)
from ...models import (
    SwapProvider as SwapProviderEnum,
)
from ..base import SwapProvider
from .models import (
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


class NearIntentsClient(SwapProvider):
    """NEAR Intents 1Click API client"""

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
        cached_tokens = await SupportedTokensCache.get(SwapProviderEnum.NEAR_INTENTS)
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
            await SupportedTokensCache.set(SwapProviderEnum.NEAR_INTENTS, tokens)
            return tokens

    @staticmethod
    def _is_address_equal(a: str | None, b: str | None) -> bool:
        if a is None and b is None:
            return True

        if a is None or b is None:
            return False

        return a.lower() == b.lower()

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

    async def get_indicative_quote(
        self, request: SwapQuoteRequest
    ) -> SwapQuoteResponse:
        near_request = to_near_intents_request(request, dry=True)

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/quote",
                json=near_request.model_dump(by_alias=True),
            )
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsQuoteResponse.model_validate(data)
            return from_near_intents_quote(near_response, request)

    async def get_firm_quote(self, request: SwapQuoteRequest) -> SwapQuoteResponse:
        near_request = to_near_intents_request(request, dry=False)

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/quote",
                json=near_request.model_dump(by_alias=True),
            )
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsQuoteResponse.model_validate(data)
            return from_near_intents_quote(near_response, request)

    async def get_swap_status(
        self, deposit_address: str, deposit_memo: str | None = None
    ) -> SwapStatusResponse:
        params = {"depositAddress": deposit_address}
        if deposit_memo:
            params["depositMemo"] = deposit_memo

        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/v0/status", params=params)
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsStatusResponse.model_validate(data)

            # Extract chain info from the original quote request
            quote_req = near_response.quote_response.quote_request
            # For now, use placeholder values - ideally we'd parse from quote_request
            source_chain = "eth.0x1"  # Placeholder
            dest_chain = "sol.0x65"  # Placeholder

            return from_near_intents_status(near_response, source_chain, dest_chain)

    async def submit_deposit_tx(
        self, request: SubmitDepositRequest
    ) -> SwapStatusResponse:
        body = {
            "txHash": request.tx_hash,
            "depositAddress": request.deposit_address,
        }

        if request.deposit_memo:
            body["memo"] = request.deposit_memo

        if request.sender_account:
            body["nearSenderAccount"] = request.sender_account

        async with self._create_client() as client:
            response = await client.post(
                f"{self.base_url}/v0/deposit/submit",
                json=body,
            )
            response.raise_for_status()
            data = response.json()

            near_response = NearIntentsStatusResponse.model_validate(data)

            # Extract chain info from the original quote request
            quote_req = near_response.quote_response.quote_request
            # For now, use placeholder values
            source_chain = "eth.0x1"
            dest_chain = "sol.0x65"

            return from_near_intents_status(near_response, source_chain, dest_chain)
