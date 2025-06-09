import httpx

from app.api.common.models import ChainId, CoinType
from app.config import settings

from .cache import CoinMapCache, PlatformMapCache, TokenPriceCache
from .models import (
    BatchTokenPriceRequests,
    CacheStatus,
    CoingeckoPlatform,
    TokenPriceRequest,
    TokenPriceResponse,
)


class CoinGeckoClient:
    def __init__(self):
        self.base_url = (
            "https://api.coingecko.com/api/v3"
            if not settings.COINGECKO_API_KEY
            else "https://pro-api.coingecko.com/api/v3"
        )

    @staticmethod
    def _create_client() -> httpx.AsyncClient:
        headers = (
            {"x-cg-pro-api-key": settings.COINGECKO_API_KEY}
            if settings.COINGECKO_API_KEY
            else None
        )
        return httpx.AsyncClient(timeout=10.0, headers=headers)

    @staticmethod
    def _deduplicate_requests(
        batch: BatchTokenPriceRequests,
    ) -> BatchTokenPriceRequests:
        """Remove duplicate requests from the batch based on chain_id, address, and coin_type."""
        seen = set()
        unique_requests = []

        for request in batch.requests:
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

        platform_map = await self.get_platform_map()
        coin_map = await self.get_coin_map(platform_map)

        coingecko_ids = {
            id
            for request in batch_to_fetch.requests
            if (
                id := await self._get_coingecko_id_from_request(
                    request, platform_map, coin_map
                )
            )
        }

        # If no coingecko ids to fetch, return cached responses
        if not coingecko_ids:
            return results

        # Fetch prices for all coingecko ids
        params = {
            "ids": ",".join(coingecko_ids),
            "vs_currencies": batch.vs_currency.value,
            "include_platform": True,
        }

        coingecko_responses = []
        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/simple/price", params=params)
            response.raise_for_status()
            data = response.json()

            for request in batch_to_fetch.requests:
                if (
                    id := await self._get_coingecko_id_from_request(
                        request, platform_map, coin_map
                    )
                ) not in data:
                    continue

                try:
                    item = TokenPriceResponse(
                        **request.model_dump(),
                        vs_currency=batch.vs_currency,
                        price=float(data[id][batch.vs_currency.value]),
                        cache_status=CacheStatus.MISS,
                    )
                except (KeyError, ValueError):
                    continue

                coingecko_responses.append(item)

        await TokenPriceCache.set(coingecko_responses)
        results.extend(coingecko_responses)
        return results

    async def _get_coingecko_id_from_request(
        self,
        request: TokenPriceRequest,
        platform_map: dict[str, CoingeckoPlatform],
        coin_map: dict[str, dict[str, str]],
    ) -> str | None:
        # Native tokens
        if request.coin_type == CoinType.BTC:
            return "bitcoin"
        elif request.coin_type == CoinType.SOL and not request.address:
            return "solana"
        elif request.coin_type == CoinType.ADA:
            return "cardano"
        elif request.coin_type == CoinType.FIL:
            return "filecoin"
        elif request.coin_type == CoinType.ZEC:
            return "zcash"

        elif request.coin_type == CoinType.ETH and not request.address:
            chain_id = request.chain_id
            if not chain_id:
                return None

            for platform in platform_map.values():
                if platform.chain_id == chain_id.value:
                    return platform.native_token_id

            return None

        elif request.coin_type in [CoinType.SOL, CoinType.ETH]:
            return coin_map.get(request.chain_id.value, {}).get(request.address.lower())

        return None

    async def get_coin_map(
        self, platform_map: dict[str, CoingeckoPlatform]
    ) -> dict[str, dict[str, str]]:
        """
        Returns a map of contract addresses to coingecko ids for all platforms.
        First checks Redis cache, then fetches from API if needed.

        Example:
        {
            "0x1": {
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "usd-coin"
            }
        }
        """
        # Try to get from Redis
        if cached_map := await CoinMapCache.get():
            return cached_map

        # Fetch from API if not in cache
        async with self._create_client() as client:
            response = await client.get(
                f"{self.base_url}/coins/list?include_platform=true"
            )
            response.raise_for_status()
            data = response.json()

            coin_map = {}
            for item in data:
                for platform_id, contract_address in item["platforms"].items():
                    if platform_id in platform_map:
                        chain_id = platform_map[platform_id].chain_id
                        if chain_id not in coin_map:
                            coin_map[chain_id] = {}
                        coin_map[chain_id][contract_address.lower()] = item[
                            "id"
                        ].lower()

            # Cache in Redis
            await CoinMapCache.set(coin_map)
            return coin_map

    async def get_platform_map(self) -> dict[str, CoingeckoPlatform]:
        # Try to get from Redis
        if cached_map := await PlatformMapCache.get():
            return cached_map

        # Fetch from API if not in cache
        async with self._create_client() as client:
            response = await client.get(f"{self.base_url}/asset_platforms")
            response.raise_for_status()
            data = response.json()

            platform_map = {}
            for item in data:
                chain_id = None
                if item["id"] == "solana":
                    chain_id = ChainId.SOLANA.value
                elif item["chain_identifier"]:
                    chain_id = hex(item["chain_identifier"])

                platform_map[item["id"]] = CoingeckoPlatform(
                    id=item["id"],
                    chain_id=chain_id,
                    native_token_id=item["native_coin_id"],
                )

            # Cache in Redis
            await PlatformMapCache.set(platform_map)
            return platform_map
