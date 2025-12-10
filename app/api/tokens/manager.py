import json
from typing import Literal

import requests
from redis.commands.search.field import TextField
from redis.commands.search.index_definition import IndexDefinition
from redis.commands.search.query import Query

from app.api.common.models import Chain, Coin, TokenInfo, TokenSource, TokenType
from app.api.tokens.contants import SPL_TOKEN_2022_PROGRAM_ID, SPL_TOKEN_PROGRAM_ID
from app.api.tokens.models import TokenSearchResponse
from app.core.cache import Cache


class TokenManager:
    key_prefix = "token"
    index_name = "token_idx"

    # Pre-computed chain lookup for O(1) access
    _chain_lookup = {chain.chain_id: chain for chain in Chain}

    @classmethod
    async def create_index(cls) -> None:
        """
        Create RediSearch index for token search capabilities.
        """
        async with Cache.get_client() as redis_client:
            index = redis_client.ft(cls.index_name)

            try:
                await index.info()
                return index
            except Exception:
                pass

            # Create index with schema for searchable fields
            schema = [
                TextField("symbol_lower", weight=2.0),
                TextField("name_lower", weight=1.5),
                TextField("address_lower", weight=1.0),
            ]

            definition = IndexDefinition(prefix=[f"{cls.key_prefix}:"])

            return await index.create_index(fields=schema, definition=definition)

    @classmethod
    async def refresh(cls) -> None:
        """
        Refresh all tokens by clearing existing data and ingesting fresh data atomically.
        """
        async with Cache.get_client() as redis_client:
            pipe = redis_client.pipeline()

            # Clear existing tokens
            await cls._clear_tokens(pipe)

            # Ingest Coingecko data
            await cls.ingest_from_coingecko(pipe)

            # Ingest Jupiter LST tokens
            await cls.ingest_from_jupiter("lst", pipe)

            # Ingest Jupiter verified tokens
            await cls.ingest_from_jupiter("verified", pipe)

            # Ingest NEAR Intents tokens
            await cls.ingest_from_near_intents(pipe)

            # Execute all operations atomically
            await pipe.execute()

    @classmethod
    async def _clear_tokens(cls, pipe) -> None:
        async with Cache.get_client() as redis_client:
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(
                    cursor, match=f"{cls.key_prefix}:*"
                )
                for key in keys:
                    pipe.delete(key)
                if cursor == 0:
                    break

            index = redis_client.ft(cls.index_name)
            try:
                await index.info()
            except Exception:
                pass
            else:
                await index.dropindex()

    @classmethod
    async def ingest_from_coingecko(cls, pipe) -> None:
        # Create index if it doesn't exist
        await cls.create_index()

        url = "https://raw.githubusercontent.com/brave/token-lists/refs/heads/main/data/v1/coingecko.json"

        response = requests.get(url, timeout=10)
        json_data = response.json()

        for raw_chain_id, tokens in json_data.items():
            for address, raw_token_info in tokens.items():
                chain = cls._chain_lookup.get(raw_chain_id)
                if not chain:
                    continue

                decimals = raw_token_info.get("decimals")
                if not decimals:
                    continue

                token_info = TokenInfo(
                    coin=chain.coin,
                    chain_id=chain.chain_id,
                    address=address,
                    name=raw_token_info["name"],
                    symbol=raw_token_info["symbol"],
                    decimals=decimals,
                    logo=raw_token_info["logo"],
                    sources=[],  # We'll add sources later
                    token_type=(
                        TokenType.ERC20
                        if chain.coin == Coin.ETH
                        else (
                            TokenType.SPL_TOKEN_2022
                            if chain.coin == Coin.SOL
                            and raw_token_info.get("token2022", False)
                            # FIXME(onyb): if token2022 is not present,
                            # we should not assume it is a SPL token.
                            #
                            # Currently, all SOL tokens are assumed to
                            # be SPL tokens.
                            else (
                                TokenType.SPL_TOKEN
                                if chain.coin == Coin.SOL
                                else TokenType.UNKNOWN
                            )
                        )
                    ),
                )

                key = cls._build_key(chain.coin, chain.chain_id, address)
                token_data = cls._prepare_token_data(token_info)

                # Get existing data for comparison
                async with Cache.get_client() as redis_client:
                    existing = await redis_client.hgetall(key)

                sources = set(json.loads(existing["sources"])) if existing else set()
                sources.add(TokenSource.COINGECKO)
                token_data["sources"] = json.dumps(sorted(list(sources)))

                if existing != token_data:
                    pipe.hset(key, mapping=token_data)

    @classmethod
    async def ingest_from_jupiter(cls, tag: Literal["lst", "verified"], pipe) -> None:
        # Create index if it doesn't exist
        await cls.create_index()

        url = f"https://lite-api.jup.ag/tokens/v2/tag?query={tag}"
        response = requests.get(url, timeout=10)
        json_data = response.json()

        for token in json_data:
            token_info = TokenInfo(
                coin=Chain.SOLANA.coin,
                chain_id=Chain.SOLANA.chain_id,
                address=token["id"],
                name=token["name"],
                symbol=token["symbol"],
                decimals=token["decimals"],
                logo=token.get("icon", ""),
                sources=[],  # We'll add sources later
                token_type=(
                    TokenType.SPL_TOKEN
                    if (program := token["tokenProgram"]) == SPL_TOKEN_PROGRAM_ID
                    else (
                        TokenType.SPL_TOKEN_2022
                        if program == SPL_TOKEN_2022_PROGRAM_ID
                        else TokenType.UNKNOWN
                    )
                ),
            )

            key = cls._build_key(Chain.SOLANA.coin, Chain.SOLANA.chain_id, token["id"])
            token_data = cls._prepare_token_data(token_info)

            async with Cache.get_client() as redis_client:
                existing = await redis_client.hgetall(key)

            sources = set(json.loads(existing["sources"])) if existing else set()
            sources.add(
                TokenSource.JUPITER_LST
                if tag == "lst"
                else TokenSource.JUPITER_VERIFIED
            )
            token_data["sources"] = json.dumps(sorted(list(sources)))

            if existing != token_data:
                pipe.hset(key, mapping=token_data)

    @classmethod
    async def ingest_from_near_intents(cls, pipe) -> None:
        # Create index if it doesn't exist
        await cls.create_index()

        # Import here to avoid circular imports
        from app.api.swap.providers.near_intents.client import NearIntentsClient

        # Get NEAR Intents client with token manager
        near_intents_client = NearIntentsClient(token_manager=cls)

        # Fetch supported tokens from NEAR Intents
        tokens = await near_intents_client.get_supported_tokens()

        # Process each token
        for token_info in tokens:
            key = cls._build_key(
                token_info.coin,
                token_info.chain_id,
                token_info.address,
            )
            async with Cache.get_client() as redis_client:
                existing = await redis_client.hgetall(key)

            sources = set(json.loads(existing["sources"])) if existing else set()
            sources.add(TokenSource.NEAR_INTENTS)
            token_info.sources = sorted(list(sources))
            token_data = cls._prepare_token_data(token_info)

            if existing:
                existing["near_intents_asset_id"] = token_data["near_intents_asset_id"]
                existing["sources"] = token_data["sources"]

                pipe.hset(key, mapping=existing)
            else:
                pipe.hset(key, mapping=token_data)

    @classmethod
    async def get(
        cls, coin: Coin, chain_id: str, address: str | None
    ) -> TokenInfo | None:
        key = cls._build_key(coin, chain_id, address)

        try:
            async with Cache.get_client() as redis_client:
                token_data = await redis_client.hgetall(key)

            if not token_data:
                return None

            return cls._parse_token_from_redis_data(key, token_data)
        except Exception as e:
            print(f"Error retrieving token: {e}")
            return None

    @classmethod
    def _build_key(cls, coin: Coin, chain_id: str, address: str | None = None) -> str:
        return ":".join(
            (
                cls.key_prefix,
                coin.value.lower(),
                chain_id.lower(),
                (address or "").lower(),
            )
        )

    @staticmethod
    def _prepare_token_data(token_info: TokenInfo) -> dict[str, str]:
        token_data = token_info.model_dump(mode="json")
        token_data["name_lower"] = token_info.name.lower()
        token_data["symbol_lower"] = token_info.symbol.lower()
        token_data["address_lower"] = (token_info.address or "").lower()

        # Store sources as JSON string
        if "sources" in token_data and isinstance(token_data["sources"], list):
            token_data["sources"] = json.dumps(token_data["sources"])

        # Convert None values to empty strings for Redis compatibility
        for key, value in token_data.items():
            if value is None:
                token_data[key] = ""

        return token_data

    @staticmethod
    def _parse_token_from_redis_data(key: str, token_data: dict[str, str]) -> TokenInfo:
        # Parse the key to extract coin and chain_id (but not address, since it's lowercased in the key)
        key_parts = key.decode("utf-8") if isinstance(key, bytes) else key
        _, coin_str, chain_id, _ = key_parts.split(":", 3)

        # Read the address from token_data to preserve case sensitivity
        address = token_data.get("address")

        return TokenInfo(
            coin=Coin(coin_str.upper()),
            chain_id=chain_id,
            address=address if address else None,
            name=token_data["name"],
            symbol=token_data["symbol"],
            decimals=int(token_data["decimals"]),
            logo=token_data.get("logo") or None,
            sources=json.loads(token_data.get("sources", "[]")),
            token_type=TokenType(token_data["token_type"]),
            near_intents_asset_id=token_data.get("near_intents_asset_id") or None,
        )

    @classmethod
    async def add(cls, token_info: TokenInfo):
        key = cls._build_key(token_info.coin, token_info.chain_id, token_info.address)
        token_data = cls._prepare_token_data(token_info)

        try:
            async with Cache.get_client() as redis_client:
                await redis_client.hset(key, mapping=token_data)
                print(f"Added/updated token at {key}")
        except Exception as e:
            print(f"Error adding token: {e}")

    @staticmethod
    def _as_response(
        result, query: str, offset: int, limit: int
    ) -> TokenSearchResponse:
        results = []
        for doc in result.docs:
            # Parse the key to extract coin and chain_id
            _, coin, chain_id, _ = doc.id.split(":")

            token_info = TokenInfo(
                coin=Coin(coin.upper()),
                chain_id=chain_id,
                address=doc.address,
                name=doc.name,
                symbol=doc.symbol.upper(),
                decimals=int(doc.decimals),
                logo=doc.logo,
                sources=json.loads(doc.sources),
                token_type=TokenType(doc.token_type),
                near_intents_asset_id=doc.near_intents_asset_id or None,
            )

            results.append(token_info)

        return TokenSearchResponse(
            results=results, total=result.total, query=query, offset=offset, limit=limit
        )

    @classmethod
    async def list_tokens(
        cls, coin: Coin, chain_id: str | None = None
    ) -> list[TokenInfo]:
        """
        List all tokens for a specific coin and optionally chain_id.
        If chain_id is None, returns all tokens for the given coin across all chains.
        """
        async with Cache.get_client() as redis_client:
            # Create the key pattern to match all tokens for this coin
            if chain_id:
                key_pattern = (
                    f"{cls.key_prefix}:{coin.value.lower()}:{chain_id.lower()}:*"
                )
            else:
                key_pattern = f"{cls.key_prefix}:{coin.value.lower()}:*"

            # Use SCAN to find all matching keys
            cursor = 0
            all_keys = []

            while True:
                cursor, keys = await redis_client.scan(
                    cursor, match=key_pattern, count=1_000
                )
                all_keys.extend(keys)
                if cursor == 0:
                    break

            if not all_keys:
                return []

            # Use pipeline to batch all HGETALL operations
            pipe = redis_client.pipeline()
            for key in all_keys:
                pipe.hgetall(key)

            # Execute all operations in one round-trip
            token_data_list = await pipe.execute()

            # Process results
            results = []
            for key, token_data in zip(all_keys, token_data_list):
                if not token_data:
                    continue

                try:
                    token_info = cls._parse_token_from_redis_data(key, token_data)
                    results.append(token_info)
                except Exception as e:
                    print(f"Error processing token key {key}: {e}")
                    continue

            return results

    @classmethod
    async def search(cls, query: str, offset: int, limit: int) -> TokenSearchResponse:
        query_lower = query.strip().lower()
        index = await cls.create_index()

        # Build comprehensive DIALECT 2 compliant search query with multiple matching strategies
        search_query = ""
        fuzz = "%" * 2

        # Unified search logic for both single and multi-word queries
        terms = query_lower.split()
        search_parts = []

        # Define search fields for different matching strategies
        fuzzy_prefix_fields = ["name_lower"]

        # 1. Exact symbol matches (highest priority - weight 5.0)
        if len(terms) == 1:
            exact_terms = [f"{term}" for term in terms]
            symbol_exact = f"@symbol_lower:({' '.join(exact_terms)})"
            search_parts.append(f"({symbol_exact}) => {{ $weight: 5.0; }}")

        # 2. Exact address matches (highest priority - weight 5.0)
        if len(terms) == 1:
            exact_terms = [f"{term}" for term in terms]
            address_exact = f"@address_lower:({' '.join(exact_terms)})"
            search_parts.append(f"({address_exact}) => {{ $weight: 5.0; }}")

        # 3. Exact name matches (high priority - weight 2.0)
        if len(terms) >= 1:
            exact_terms = [f"{term}" for term in terms]
            name_exact = f"@name_lower:({' '.join(exact_terms)})"
            search_parts.append(f"({name_exact}) => {{ $weight: 2.0; }}")

        # 4. Prefix/infix matches for name field (lower priority - weight 1.0)
        if len(terms) >= 1:
            prefix_terms = [f"*{term}*" for term in terms]
            for field in fuzzy_prefix_fields:
                prefix_query = f"@{field}:({' '.join(prefix_terms)})"
                search_parts.append(f"({prefix_query}) => {{ $weight: 1.0; }}")

        # 5. Fuzzy matches for name field (lowest priority - weight 0.5)
        if len(terms) >= 1:
            fuzzy_terms = [f"{fuzz}{term}{fuzz}" for term in terms]
            for field in fuzzy_prefix_fields:
                fuzzy_query = f"@{field}:({' '.join(fuzzy_terms)})"
                search_parts.append(f"({fuzzy_query}) => {{ $weight: 0.5; }}")

        search_query = " | ".join(search_parts)

        if not search_query:
            search_query = "*"

        q = Query(search_query).dialect(2).paging(offset, limit)
        result = await index.search(q)

        return cls._as_response(result, query, offset, limit)

    @staticmethod
    async def mock_fetch_from_blockchain(
        coin: Coin, chain_id: str, address: str
    ) -> TokenInfo | None:
        return TokenInfo(
            coin=coin,
            chain_id=chain_id.lower(),
            address=address,
            name="Mock Token",
            symbol="MTK",
            decimals=18,
            logo="https://example.com/mock-logo.png",
            sources=[TokenSource.UNKNOWN],
        )
