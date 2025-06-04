import httpx

from app.api.common.models import ChainId, CoinType
from app.config import settings

from .models import (
    TokenPriceRequest,
    TokenPriceResponse,
    CacheStatus,
    BatchTokenPriceRequests,
)
from .cache import TokenPriceCache


class CoinGeckoClient:
    def __init__(self):
        self.base_url = (
            "https://api.coingecko.com/api/v3"
            if not settings.COINGECKO_API_KEY
            else "https://pro-api.coingecko.com/api/v3"
        )

    def _create_client(self) -> httpx.AsyncClient:
        headers = (
            {"x-cg-pro-api-key": settings.COINGECKO_API_KEY}
            if settings.COINGECKO_API_KEY
            else None
        )
        return httpx.AsyncClient(timeout=10.0, headers=headers)

    def _deduplicate_requests(
        self, batch: BatchTokenPriceRequests
    ) -> BatchTokenPriceRequests:
        """Remove duplicate requests from the batch based on chain_id, address, and coin_type."""
        seen = set()
        unique_requests = []

        for request in batch:
            # Create a unique key for each request
            key = (request.chain_id, request.address, request.coin_type)
            if key not in seen:
                seen.add(key)
                unique_requests.append(request)

        return BatchTokenPriceRequests(
            requests=unique_requests, vs_currency=batch.vs_currency
        )

    async def get_prices(
        self, batch: BatchTokenPriceRequests
    ) -> list[TokenPriceResponse]:
        """Get prices for multiple tokens using CoinGecko API"""
        # Deduplicate requests first
        batch = self._deduplicate_requests(batch)

        # Check cache for all tokens first
        cached_responses, batch_to_fetch = await TokenPriceCache.get(batch)
        results = list(cached_responses)

        if batch_to_fetch.is_empty():
            return results

        # Group tokens by type for efficient fetching
        non_native_tokens = [
            request
            for request in batch_to_fetch
            if not self._get_native_token_id(request)
        ]
        native_tokens = [
            request for request in batch_to_fetch if self._get_native_token_id(request)
        ]

        if native_tokens:
            native_responses = await self._get_native_token_prices(
                BatchTokenPriceRequests(
                    requests=native_tokens, vs_currency=batch.vs_currency
                )
            )
            if native_responses:
                await TokenPriceCache.set(native_responses)
                results.extend(native_responses)

        if non_native_tokens:
            token_responses = await self._get_non_native_token_prices(
                BatchTokenPriceRequests(
                    requests=non_native_tokens, vs_currency=batch.vs_currency
                )
            )
            if token_responses:
                await TokenPriceCache.set(token_responses)
                results.extend(token_responses)

        return results

    async def _get_native_token_prices(
        self, batch: BatchTokenPriceRequests
    ) -> list[TokenPriceResponse]:
        if batch.is_empty():
            return []

        url = f"{self.base_url}/simple/price"
        params = {
            "ids": ",".join(self._get_native_token_id(request) for request in batch),
            "vs_currencies": batch.vs_currency.value,
        }

        async with self._create_client() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results = []
            for request in batch:
                try:
                    price = float(
                        data[self._get_native_token_id(request)][
                            batch.vs_currency.value
                        ]
                    )
                    results.append(
                        TokenPriceResponse(
                            **request.model_dump(),
                            vs_currency=batch.vs_currency,
                            price=price,
                            cache_status=CacheStatus.MISS,
                        )
                    )
                except (KeyError, ValueError):
                    continue

            return results

    async def _get_non_native_token_prices(
        self, batch: BatchTokenPriceRequests
    ) -> list[TokenPriceResponse]:
        if batch.is_empty():
            return []

        # Group tokens by chain
        chain_batches: dict[ChainId, BatchTokenPriceRequests] = {}
        for request in batch:
            # Skip native tokens
            if self._get_native_token_id(request):
                continue

            if request.chain_id not in chain_batches:
                chain_batches[request.chain_id] = (
                    BatchTokenPriceRequests.from_vs_currency(batch.vs_currency)
                )
            chain_batches[request.chain_id].add(request)

        results: list[TokenPriceResponse] = []

        # Fetch prices for each chain
        for chain_id, chain_batch in chain_batches.items():
            platform = self._get_platform(chain_id)
            addresses = [t.address for t in chain_batch]

            url = f"{self.base_url}/simple/token_price/{platform}"
            params = {
                "contract_addresses": ",".join(addresses),
                "vs_currencies": chain_batch.vs_currency.value,
            }

            async with self._create_client() as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                for request in chain_batch:
                    try:
                        price = float(
                            data[request.address.lower()][chain_batch.vs_currency.value]
                        )
                        results.append(
                            TokenPriceResponse(
                                **request.model_dump(),
                                vs_currency=chain_batch.vs_currency,
                                price=price,
                                cache_status=CacheStatus.MISS,
                            )
                        )
                    except (KeyError, ValueError):
                        # KeyError: address not found in price data
                        # ValueError: price data is not a float
                        continue

        return results

    @staticmethod
    def _get_platform(chain_id: ChainId) -> str:
        """Convert ChainId to CoinGecko platform name"""
        platform_map = {
            ChainId.ETHEREUM: "ethereum",
            ChainId.BASE: "base",
            ChainId.OPTIMISM: "optimistic-ethereum",
            ChainId.ARBITRUM: "arbitrum-one",
            ChainId.POLYGON: "polygon-pos",
            ChainId.SOLANA: "solana",
        }

        if chain_id not in platform_map:
            raise ValueError(f"Unsupported chain ID for CoinGecko: {chain_id}")

        return platform_map[chain_id]

    @staticmethod
    def _get_native_token_id(request: TokenPriceRequest) -> str | None:
        """Get native token ID for CoinGecko"""
        if request.coin_type == CoinType.BTC:
            return "bitcoin"
        elif request.coin_type == CoinType.ETH and not request.address:
            return "ethereum"
        elif request.coin_type == CoinType.SOL and not request.address:
            return "solana"
        elif request.coin_type == CoinType.ADA:
            return "cardano"
        elif request.coin_type == CoinType.FIL:
            return "filecoin"
        elif request.coin_type == CoinType.ZEC:
            return "zcash"

        return None
