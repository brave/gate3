import httpx
import asyncio

from app.api.common.models import ChainId, CoinType
from .models import (
    BatchTokenPriceRequests,
    TokenPriceRequest,
    TokenPriceResponse,
    CacheStatus,
    VsCurrency,
)
from .cache import JupiterPriceCache
from .coingecko import CoinGeckoClient
from .constants import JUPITER_CHUNK_SIZE, JUPITER_MAX_CONCURRENT_REQUESTS
from .utils import chunk_sequence


class JupiterClient:
    def __init__(self):
        self.base_url = "https://lite-api.jup.ag"

    @staticmethod
    def _create_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=10.0)

    @staticmethod
    async def filter(
        batch: BatchTokenPriceRequests,
    ) -> tuple[BatchTokenPriceRequests, BatchTokenPriceRequests]:
        """Filter batch to return two batches: available in Jupiter and not available"""
        available_batch = BatchTokenPriceRequests.from_vs_currency(batch.vs_currency)
        unavailable_batch = BatchTokenPriceRequests.from_vs_currency(batch.vs_currency)

        for request in batch.requests:
            # Jupiter Price API can only handle Solana tokens with addresses
            if (
                request.coin_type == CoinType.SOL
                and request.chain_id == ChainId.SOLANA
                and request.address
            ):
                available_batch.add(request)
            else:
                unavailable_batch.add(request)

        return available_batch, unavailable_batch

    async def get_prices(
        self,
        batch: BatchTokenPriceRequests,
        coingecko_client: CoinGeckoClient,
    ) -> list[TokenPriceResponse]:
        """Get prices for multiple tokens using Jupiter API"""
        if batch.is_empty():
            return []

        # Check cache first
        cached_responses, batch_to_fetch = await JupiterPriceCache.get(batch)
        results = list(cached_responses)

        if batch_to_fetch.is_empty():
            return results

        # Get addresses to fetch
        addresses = [
            request.address for request in batch_to_fetch.requests if request.address
        ]
        if not addresses:
            return results

        # Split addresses into chunks
        address_chunks = chunk_sequence(addresses, JUPITER_CHUNK_SIZE)

        # Process chunks in parallel with controlled concurrency
        semaphore = asyncio.Semaphore(JUPITER_MAX_CONCURRENT_REQUESTS)

        async def fetch_chunk(chunk: list[str]) -> dict:
            async with semaphore:
                params = {"ids": ",".join(chunk)}
                async with self._create_client() as client:
                    response = await client.get(
                        f"{self.base_url}/price/v2", params=params
                    )
                    response.raise_for_status()
                    return response.json()["data"]

        chunk_results = await asyncio.gather(
            *[fetch_chunk(chunk) for chunk in address_chunks], return_exceptions=True
        )

        # Combine results from all chunks
        combined_data = {}
        for result in chunk_results:
            if isinstance(result, Exception):
                continue
            combined_data.update(result)

        # If vs_currency is not USD, we need to fetch USDC price in that currency
        usdc_multiplier = 1.0
        if batch.vs_currency != VsCurrency.USD:
            usdc_request = TokenPriceRequest(
                coin_type=CoinType.SOL,
                chain_id=ChainId.SOLANA,
                address="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC on Solana
            )
            usdc_batch = BatchTokenPriceRequests(
                requests=[usdc_request], vs_currency=batch.vs_currency
            )
            usdc_responses = await coingecko_client.get_prices(usdc_batch)
            if usdc_responses:
                usdc_multiplier = usdc_responses[0].price

        # Process results
        jupiter_responses = []
        for request in batch_to_fetch.requests:
            if not request.address or request.address not in combined_data:
                continue

            try:
                price = float(combined_data[request.address]["price"]) * usdc_multiplier
                item = TokenPriceResponse(
                    **request.model_dump(),
                    vs_currency=batch.vs_currency,
                    price=price,
                    cache_status=CacheStatus.MISS,
                )
                jupiter_responses.append(item)
            except (KeyError, ValueError):
                continue

        # Cache the responses
        await JupiterPriceCache.set(jupiter_responses)
        results.extend(jupiter_responses)
        return results
