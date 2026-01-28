import asyncio
import logging

import httpx
from pydantic import ValidationError

from app.api.common.models import Chain, Coin
from app.config import settings

from .cache import CoingeckoPriceCache, CoinMapCache, PlatformMapCache
from .constants import COINGECKO_CHUNK_SIZE, COINGECKO_MAX_CONCURRENT_REQUESTS
from .models import (
    BatchTokenPriceRequests,
    CacheStatus,
    CoingeckoPlatform,
    PriceSource,
    TokenPriceRequest,
    TokenPriceResponse,
)
from .utils import chunk_sequence

logger = logging.getLogger(__name__)


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

    async def filter(
        self, batch: BatchTokenPriceRequests
    ) -> tuple[BatchTokenPriceRequests, BatchTokenPriceRequests]:
        """Filter batch to return two batches: available in CoinGecko and not available"""
        available_batch = BatchTokenPriceRequests.from_vs_currency(batch.vs_currency)
        unavailable_batch = BatchTokenPriceRequests.from_vs_currency(batch.vs_currency)

        # Get platform and coin maps
        platform_map = await self.get_platform_map()
        coin_map = await self.get_coin_map(platform_map)

        for request in batch.requests:
            # Check if this token is available in CoinGecko
            if await self._get_coingecko_id_from_request(
                request, platform_map, coin_map
            ):
                available_batch.add(request)
            else:
                unavailable_batch.add(request)

        return available_batch, unavailable_batch

    async def get_prices(
        self, batch: BatchTokenPriceRequests
    ) -> list[TokenPriceResponse]:
        """Get prices for multiple tokens using CoinGecko API"""
        # Check cache for all tokens first
        cached_responses, batch_to_fetch = await CoingeckoPriceCache.get(batch)
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

        # Split coingecko_ids into chunks
        id_chunks = chunk_sequence(list(coingecko_ids), COINGECKO_CHUNK_SIZE)

        # Process chunks in parallel with controlled concurrency
        semaphore = asyncio.Semaphore(COINGECKO_MAX_CONCURRENT_REQUESTS)

        async def fetch_chunk(chunk: list[str]) -> dict:
            async with semaphore:
                params = {
                    "ids": ",".join(chunk),
                    "vs_currencies": batch.vs_currency.value,
                    "include_platform": True,
                    "include_24hr_change": True,
                }
                async with self._create_client() as client:
                    response = await client.get(
                        f"{self.base_url}/simple/price", params=params
                    )
                    response.raise_for_status()
                    return response.json()

        chunk_results = await asyncio.gather(
            *[fetch_chunk(chunk) for chunk in id_chunks], return_exceptions=True
        )

        # Combine results from all chunks
        combined_data = {}
        for result in chunk_results:
            if isinstance(result, Exception):
                continue
            combined_data.update(result)

        coingecko_responses = []
        for request in batch_to_fetch.requests:
            if (
                id := await self._get_coingecko_id_from_request(
                    request, platform_map, coin_map
                )
            ) not in combined_data:
                continue

            try:
                response = combined_data[id]
                vs_currency_key = batch.vs_currency.lower()
                percentage_change_24h = response.get(f"{vs_currency_key}_24h_change")
                item = TokenPriceResponse(
                    **request.model_dump(),
                    vs_currency=batch.vs_currency,
                    price=float(response[vs_currency_key]),
                    percentage_change_24h=(
                        float(percentage_change_24h)
                        if percentage_change_24h is not None
                        else None
                    ),
                    cache_status=CacheStatus.MISS,
                    source=PriceSource.COINGECKO,
                )
            except (KeyError, ValueError):
                continue

            coingecko_responses.append(item)

        await CoingeckoPriceCache.set(coingecko_responses)
        results.extend(coingecko_responses)
        return results

    async def _get_coingecko_id_from_request(
        self,
        request: TokenPriceRequest,
        platform_map: dict[str, CoingeckoPlatform],
        coin_map: dict[str, dict[str, str]],
    ) -> str | None:
        # Native tokens
        chain = Chain.get(request.coin, request.chain_id)
        if chain == Chain.BITCOIN:
            return "bitcoin"

        elif chain == Chain.CARDANO:
            return "cardano"

        elif chain == Chain.FILECOIN:
            return "filecoin"

        elif chain == Chain.ZCASH:
            return "zcash"

        elif chain == Chain.SOLANA and not request.address:
            return "solana"

        # Native asset on EVM chains
        elif request.coin == Coin.ETH and not request.address:
            for platform in platform_map.values():
                if platform.chain_id == request.chain_id and platform.native_token_id:
                    return platform.native_token_id

            return None

        # EVM and Solana tokens
        elif request.coin in [Coin.SOL, Coin.ETH] and request.address:
            return coin_map.get(request.chain_id, {}).get(request.address.lower())

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
                    chain_id = Chain.SOLANA.chain_id
                elif item["chain_identifier"]:
                    chain_id = hex(item["chain_identifier"])

                # Skip entries that fail Pydantic validation (e.g., null native_token_id)
                try:
                    platform_map[item["id"]] = CoingeckoPlatform(
                        id=item["id"],
                        chain_id=chain_id,
                        native_token_id=item["native_coin_id"],
                    )
                except ValidationError as e:
                    logger.error(
                        f"Skipping item {item.get('id')} in platform map due to validation error: {e}"
                    )
                    continue

            # Cache in Redis
            await PlatformMapCache.set(platform_map)
            return platform_map
