import json

import httpx
from fastapi import APIRouter, Path, Query

from app.api.common.models import Chain, Coin
from app.api.nft.models import (
    AlchemyNFT,
    AlchemyNFTResponse,
    AlchemyTokenType,
    SimpleHashCollection,
    SimpleHashContract,
    SimpleHashExtraMetadata,
    SimpleHashNFT,
    SimpleHashNFTResponse,
    SimpleHashTokenType,
    SolanaAsset,
    SolanaAssetMerkleProof,
    SolanaAssetRawContent,
    SolanaAssetResponse,
    TraitAttribute,
)
from app.config import settings

router = APIRouter(prefix="/api/nft")
simplehash_router = APIRouter(prefix="/simplehash/api/v0")

with open("data/cg-nfts.json", "r") as f:
    cg_nfts = json.load(f)

# Chain mapping dictionaries
_SIMPLEHASH_TO_CHAIN = {chain.simplehash_id: chain for chain in Chain}


def _get_spam_score_for_solana_collection(collection_name: str | None) -> int:
    if collection_name is None:
        return 0

    spam_keywords = {"airdrop", "lucky box", "reward box"}
    collection_name_lower = collection_name.lower()
    return (
        1 if any(keyword in collection_name_lower for keyword in spam_keywords) else 0
    )


def _token_type_to_simplehash(token_type: AlchemyTokenType) -> SimpleHashTokenType:
    if token_type == AlchemyTokenType.ERC721:
        return SimpleHashTokenType.ERC721
    elif token_type == AlchemyTokenType.ERC1155:
        return SimpleHashTokenType.ERC1155

    raise ValueError(f"Unsupported token type: {token_type}")


def _transform_alchemy_to_simplehash(
    alchemy_nft: AlchemyNFT, chain: Chain
) -> SimpleHashNFT:
    contract = alchemy_nft.contract
    image = alchemy_nft.image or {}
    raw = alchemy_nft.raw or {}
    metadata = (
        {} if raw.metadata is None or isinstance(raw.metadata, str) else raw.metadata
    )
    attributes = metadata.attributes if metadata else []
    external_url = metadata.external_url if metadata else None
    properties = metadata.properties if metadata else {}

    # Transform attributes to SimpleHash format
    transformed_attributes = [
        TraitAttribute(trait_type=attr.trait_type, value=attr.value)
        for attr in attributes
    ]

    # Create collection info
    collection = SimpleHashCollection(
        name=contract.name or "", spam_score=(1 if contract.is_spam else 0)
    )

    # Create contract info
    contract_info = SimpleHashContract(
        type=_token_type_to_simplehash(alchemy_nft.token_type),
        name=contract.name,
        symbol=contract.symbol,
    )

    extra_metadata = SimpleHashExtraMetadata(
        attributes=transformed_attributes,
        properties=properties,
        image_original_url=image.original_url,
        animation_original_url=None,
        metadata_original_url=alchemy_nft.token_uri,
    )

    return SimpleHashNFT(
        chain=chain.simplehash_id,
        contract_address=contract.address,
        token_id=alchemy_nft.token_id,
        name=alchemy_nft.name,
        description=alchemy_nft.description,
        image_url=image.cached_url,
        background_color=None,
        external_url=external_url,
        contract=contract_info,
        collection=collection,
        extra_metadata=extra_metadata,
    )


async def _transform_solana_asset_to_simplehash(asset: SolanaAsset) -> SimpleHashNFT:
    # Skip burnt NFTs
    if asset.burnt:
        return None

    name = asset.content.metadata.name
    symbol = asset.content.metadata.symbol
    description = asset.content.metadata.description

    # Get collection info from grouping
    collection_name = next(
        (
            group.collection_metadata.name
            for group in asset.grouping
            if group.group_key == "collection" and group.collection_metadata
        ),
        "",
    )

    # Extract image URL from content
    image_url = None
    if asset.content.links.image:
        image_url = asset.content.links.image
    elif asset.content.files:
        image_url = next(
            (
                file.uri
                for file in asset.content.files
                if file.mime.startswith("image/") and file.uri
            ),
            None,
        )

    if not any([name, symbol, description, image_url]):
        with httpx.AsyncClient() as client:
            raw_content_response = await client.get(asset.content.json_uri)
            raw_content_response.raise_for_status()
            raw_content_data = SolanaAssetRawContent.model_validate(
                raw_content_response.json()
            )

            name = name or raw_content_data.name
            symbol = symbol or raw_content_data.symbol
            description = description or raw_content_data.description
            image_url = image_url or raw_content_data.image

    return SimpleHashNFT(
        chain=Chain.SOLANA.simplehash_id,
        contract_address=asset.id,
        token_id=None,
        name=name,
        description=description,
        image_url=image_url,
        background_color=None,
        external_url=asset.content.links.external_url,
        contract=SimpleHashContract(
            type=SimpleHashTokenType.NON_FUNGIBLE,
            name=name,
            symbol=symbol,
        ),
        collection=SimpleHashCollection(
            name=collection_name,
            spam_score=_get_spam_score_for_solana_collection(collection_name),
        ),
        extra_metadata=SimpleHashExtraMetadata(
            attributes=asset.content.metadata.attributes,
            properties={},
            image_original_url=image_url,
            animation_original_url=None,
            metadata_original_url=asset.content.json_uri,
        ),
    )


@router.get("/v1/getNFTsForOwner", response_model=SimpleHashNFTResponse)
async def get_nfts_by_owner(
    wallet_address: str = Query(
        ..., description="The wallet address to fetch NFTs for"
    ),
    chains: list[str] = Query(
        ..., description="List of chains to fetch NFTs from in format coin.chain_id"
    ),
    page_key: str | None = Query(None, description="Page key for pagination"),
    page_size: int = Query(50, description="Number of NFTs to fetch per page"),
) -> SimpleHashNFTResponse:
    """
    Fetch NFTs owned by a wallet address across multiple chains using Alchemy API.
    The response is transformed to match the SimpleHash API format.
    """
    if not settings.ALCHEMY_API_KEY:
        raise ValueError("ALCHEMY_API_KEY is not configured")

    nfts = []
    next_page_key = None

    async with httpx.AsyncClient() as client:
        for chain_str in chains:
            coin, chain_id = chain_str.split(".")
            chain = Chain.get(coin, chain_id)
            if not chain or not chain.has_nft_support:
                continue

            if chain == Chain.SOLANA:
                # Handle Solana NFTs differently
                url = f"https://solana-mainnet.g.alchemy.com/v2/{settings.ALCHEMY_API_KEY}"
                params = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAssetsByOwner",
                    "params": {
                        "ownerAddress": wallet_address,
                        "limit": page_size,
                        "options": {
                            "showUnverifiedCollections": False,
                            "showCollectionMetadata": True,
                        },
                    },
                }
                if page_key:
                    params["params"]["page"] = page_key

                response = await client.post(url, json=params)
                response.raise_for_status()
                json_response = response.json()
                if "error" in json_response:
                    raise ValueError(f"Alchemy API error: {json_response['error']}")

                solana_response = SolanaAssetResponse.model_validate(
                    json_response["result"]
                )

                # Transform Solana assets to SimpleHash format
                for asset in solana_response.items:
                    if transformed_nft := await _transform_solana_asset_to_simplehash(
                        asset
                    ):
                        nfts.append(transformed_nft)

                next_page_key = page_key + 1 if page_key else None
            else:
                # Handle other chains as before
                url = f"https://{chain.alchemy_id}.g.alchemy.com/nft/v3/{settings.ALCHEMY_API_KEY}/getNFTsForOwner"
                params = httpx.QueryParams(
                    owner=wallet_address,
                    pageSize=page_size,
                    withMetadata=True,
                )
                if page_key:
                    params = params.set("pageKey", page_key)

                response = await client.get(url, params=params)
                response.raise_for_status()

                json_response = response.json()
                data = AlchemyNFTResponse.model_validate(json_response)

                # Transform NFTs
                for nft in data.owned_nfts:
                    nfts.append(_transform_alchemy_to_simplehash(nft, chain))

                # Update next page key
                if data.page_key:
                    next_page_key = data.page_key

    return SimpleHashNFTResponse(next_cursor=next_page_key, nfts=nfts)


@router.get("/v1/getNFTsByIds", response_model=SimpleHashNFTResponse)
async def get_nfts_by_ids(
    ids: str = Query(
        ...,
        description="Comma separated list of NFT IDs in format coin.chain_id.address for Solana or coin.chain_id.address.token_id for EVM chains",
    ),
) -> SimpleHashNFTResponse:
    """
    Fetch NFTs by their IDs using Alchemy API.
    The response is transformed to match the SimpleHash API format.
    """
    if not settings.ALCHEMY_API_KEY:
        raise ValueError("ALCHEMY_API_KEY is not configured")

    nft_ids_list = ids.split(",")

    nfts = []
    solana_nfts = []
    other_nfts = []

    # Separate Solana and other chain NFTs
    for nft_id in nft_ids_list:
        # Skip empty strings from trailing commas
        if not nft_id.strip():
            continue

        parts = nft_id.split(".")

        # Skip malformed IDs that don't have enough parts
        if len(parts) < 2:
            continue

        coin = parts[0]
        chain_id = parts[1]

        chain = Chain.get(coin, chain_id)
        if not chain:
            continue

        if chain == Chain.SOLANA:  # Solana chain ID
            # Skip malformed Solana IDs that don't have exactly 3 parts
            if len(parts) != 3:
                continue
            solana_nfts.append(parts[-1])
        else:
            other_nfts.append(nft_id)

    async with httpx.AsyncClient() as client:
        # Handle Solana NFTs
        if solana_nfts:
            url = f"https://solana-mainnet.g.alchemy.com/v2/{settings.ALCHEMY_API_KEY}"
            params = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAssets",
                "params": {"ids": solana_nfts},
            }

            response = await client.post(url, json=params)
            response.raise_for_status()
            json_response = response.json()
            if "error" in json_response:
                raise ValueError(f"Alchemy API error: {json_response['error']}")

            solana_assets = []
            for nft_data in json_response["result"]:
                solana_assets.append(SolanaAsset.model_validate(nft_data))

            # Transform Solana assets to SimpleHash format
            for solana_asset in solana_assets:
                if transformed_nft := await _transform_solana_asset_to_simplehash(
                    solana_asset
                ):
                    nfts.append(transformed_nft)

        # Handle other chain NFTs
        if other_nfts:
            # Group NFTs by chain
            chain_nfts = {}
            for nft_id in other_nfts:
                parts = nft_id.split(".")

                # Skip malformed EVM IDs that don't have exactly 4 parts
                if len(parts) != 4:
                    continue

                coin, chain_id, contract_address, token_id = parts

                # Skip if token_id is empty (malformed input like "eth.0x1.0xabc.")
                if not token_id.strip():
                    continue

                chain = Chain.get(coin, chain_id)
                if not chain:
                    continue

                if chain.alchemy_id not in chain_nfts:
                    chain_nfts[chain.alchemy_id] = []
                chain_nfts[chain.alchemy_id].append((contract_address, token_id))

            # Fetch NFTs for each chain
            for alchemy_id, nft_list in chain_nfts.items():
                url = f"https://{alchemy_id}.g.alchemy.com/nft/v3/{settings.ALCHEMY_API_KEY}/getNFTMetadataBatch"

                # Prepare batch request
                tokens = [
                    {"contractAddress": contract_address, "tokenId": token_id}
                    for contract_address, token_id in nft_list
                ]

                response = await client.post(url, json={"tokens": tokens})
                response.raise_for_status()

                json_response = response.json()

                for nft_data in json_response["nfts"]:
                    alchemy_nft = AlchemyNFT.model_validate(nft_data)
                    nfts.append(_transform_alchemy_to_simplehash(alchemy_nft, chain))

    return SimpleHashNFTResponse(next_cursor=None, nfts=nfts)


@router.get("/v1/getSolanaAssetProof", response_model=SolanaAssetMerkleProof)
async def get_solana_asset_proof(
    token_address: str = Query(
        ..., description="The token address to fetch the proof for"
    ),
) -> SolanaAssetMerkleProof:
    async with httpx.AsyncClient() as client:
        url = f"https://solana-mainnet.g.alchemy.com/v2/{settings.ALCHEMY_API_KEY}"
        params = {
            "jsonrpc": "2.0",
            "method": "getAssetProof",
            "params": [token_address],
            "id": 1,
        }
        response = await client.post(url, json=params)
        response.raise_for_status()
        json_response = response.json()

        if error := json_response.get("error"):
            raise ValueError(f"Alchemy API error: {error}")

        return SolanaAssetMerkleProof.model_validate(json_response["result"])


@simplehash_router.get("/nfts/owners", response_model=SimpleHashNFTResponse)
async def get_simplehash_nfts_by_owner(
    wallet_addresses: list[str] = Query(
        ..., description="The wallet addresses to fetch NFTs for"
    ),
    chains: list[str] | None = Query(
        ..., description="List of chains to fetch NFTs from"
    ),
    cursor: str | None = Query(None, description="Cursor for pagination"),
) -> SimpleHashNFTResponse:
    filtered_chains = {
        chain_str for chain_raw in (chains or []) for chain_str in chain_raw.split(",")
    }

    internal_chains = {
        f"{chain.coin.value.lower()}.{chain.chain_id}"
        for chain_str in filtered_chains
        if (chain := _SIMPLEHASH_TO_CHAIN.get(chain_str))
    }

    # Call the internal function directly instead of redirecting
    return await get_nfts_by_owner(
        wallet_address=wallet_addresses[0],
        chains=list(internal_chains),
        page_key=cursor,
        page_size=50,  # Use default page size
    )


@simplehash_router.get(
    "/nfts/proof/solana/{token_address}", response_model=SolanaAssetMerkleProof
)
async def get_simplehash_compressed_nft_proof(
    token_address: str = Path(
        ..., description="The token address to fetch the proof for"
    ),
) -> SolanaAssetMerkleProof:
    # Call the internal function directly instead of redirecting
    return await get_solana_asset_proof(token_address=token_address)


@simplehash_router.get("/nfts/assets", response_model=SimpleHashNFTResponse)
async def get_simplehash_nfts_by_ids(
    nft_ids: str = Query(
        ...,
        description="Comma separated list of NFT IDs in format <chain>.<address> for Solana or <chain>.<address>.<token_id> for EVM chains",
    ),
) -> SimpleHashNFTResponse:
    """
    SimpleHash adapter for fetching NFTs by their IDs.
    Converts SimpleHash format NFT IDs to internal format.
    """
    # Convert SimpleHash format to internal format
    nft_ids_list = nft_ids.split(",")
    internal_nft_ids = []
    for nft_id in nft_ids_list:
        # Skip empty strings from trailing commas
        if not nft_id.strip():
            continue

        parts = nft_id.split(".")

        # Skip malformed IDs that don't have enough parts
        if len(parts) < 2:
            continue

        simplehash_id = parts[0]

        chain = _SIMPLEHASH_TO_CHAIN.get(simplehash_id)
        if chain is None:
            continue

        if not chain.has_nft_support:
            continue

        if chain == Chain.SOLANA:
            # Skip malformed Solana IDs that don't have exactly 2 parts (chain.address)
            if len(parts) != 2:
                continue
            # For Solana: chain.address -> coin.chain_id.address
            internal_nft_ids.append(
                f"{chain.coin.value.lower()}.{chain.chain_id}.{parts[1]}"
            )
        elif chain.coin == Coin.ETH:
            # Skip malformed EVM IDs that don't have exactly 3 parts (chain.address.token_id)
            if len(parts) != 3:
                continue
            # For EVM chains: chain.address.token_id -> coin.chain_id.address.token_id
            internal_nft_ids.append(
                f"{chain.coin.value.lower()}.{chain.chain_id}.{parts[1]}.{parts[2]}"
            )
        else:
            # We don't support NFTs on other chains yet
            continue

    # Call the internal function directly instead of redirecting
    return await get_nfts_by_ids(ids=",".join(internal_nft_ids))
