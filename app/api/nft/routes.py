import httpx
from fastapi import APIRouter, Query, Path
from fastapi.responses import RedirectResponse
from app.api.common.models import ChainId
from app.api.nft.models import (
    TraitAttribute,
    SimpleHashChain,
    SimpleHashNFT,
    SimpleHashNFTResponse,
    SimpleHashTokenType,
    SimpleHashContract,
    SimpleHashCollection,
    SimpleHashExtraMetadata,
    AlchemyNFTResponse,
    AlchemyNFT,
    AlchemyTokenType,
    AlchemyChain,
    SolanaAssetMerkleProof,
    SolanaAssetResponse,
    SolanaAsset,
    SolanaAssetRawContent,
)
from app.config import settings


router = APIRouter(prefix="/nft")
simplehash_router = APIRouter(prefix="/api/v0")

# Chain mapping dictionaries
_CHAIN_ID_TO_SIMPLEHASH = {
    ChainId.ETHEREUM: SimpleHashChain.ETHEREUM,
    ChainId.POLYGON: SimpleHashChain.POLYGON,
    ChainId.BASE: SimpleHashChain.BASE,
    ChainId.OPTIMISM: SimpleHashChain.OPTIMISM,
    ChainId.ARBITRUM: SimpleHashChain.ARBITRUM,
    ChainId.SOLANA: SimpleHashChain.SOLANA,
}

_SIMPLEHASH_TO_CHAIN_ID = {v: k for k, v in _CHAIN_ID_TO_SIMPLEHASH.items()}

_CHAIN_ID_TO_ALCHEMY = {
    ChainId.ETHEREUM: AlchemyChain.ETHEREUM,
    ChainId.POLYGON: AlchemyChain.POLYGON,
    ChainId.BASE: AlchemyChain.BASE,
    ChainId.OPTIMISM: AlchemyChain.OPTIMISM,
    ChainId.ARBITRUM: AlchemyChain.ARBITRUM,
    ChainId.SOLANA: AlchemyChain.SOLANA,
}


def _chain_id_to_simplehash(chain_id: ChainId) -> SimpleHashChain:
    if chain := _CHAIN_ID_TO_SIMPLEHASH.get(chain_id):
        return chain
    raise ValueError(f"Unsupported ChainId: {chain_id.value}")


def _simplehash_chain_to_chain_id(chain: SimpleHashChain) -> ChainId:
    if chain_id := _SIMPLEHASH_TO_CHAIN_ID.get(chain):
        return chain_id
    raise ValueError(f"Unsupported SimpleHashChain: {chain.value}")


def _chain_id_to_alchemy_chain(chain_id: ChainId) -> AlchemyChain:
    if chain := _CHAIN_ID_TO_ALCHEMY.get(chain_id):
        return chain
    raise ValueError(f"Unsupported ChainId: {chain_id.value}")


def _token_type_to_simplehash(token_type: AlchemyTokenType) -> SimpleHashTokenType:
    if token_type == AlchemyTokenType.ERC721:
        return SimpleHashTokenType.ERC721
    elif token_type == AlchemyTokenType.ERC1155:
        return SimpleHashTokenType.ERC1155

    raise ValueError(f"Unsupported token type: {token_type}")


def _transform_alchemy_to_simplehash(
    alchemy_nft: AlchemyNFT, chain_id: ChainId
) -> SimpleHashNFT:
    contract = alchemy_nft.contract
    image = alchemy_nft.image or {}
    raw = alchemy_nft.raw or {}
    metadata = raw.metadata or {}
    attributes = metadata.attributes or []

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
        properties=metadata.properties,
        image_original_url=image.original_url,
        animation_original_url=None,
        metadata_original_url=alchemy_nft.token_uri,
    )

    chain = _chain_id_to_simplehash(chain_id)

    return SimpleHashNFT(
        chain=chain,
        contract_address=contract.address,
        token_id=alchemy_nft.token_id,
        name=alchemy_nft.name,
        description=alchemy_nft.description,
        image_url=image.cached_url,
        background_color=None,
        external_url=metadata.external_url,
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
        chain=SimpleHashChain.SOLANA,
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
            spam_score=0,
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
    chains: list[ChainId] = Query(..., description="List of chains to fetch NFTs from"),
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
        for chain_id in chains:
            if chain_id == ChainId.SOLANA:
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
                alchemy_chain = _chain_id_to_alchemy_chain(chain_id)
                url = f"https://{alchemy_chain.value}.g.alchemy.com/nft/v3/{settings.ALCHEMY_API_KEY}/getNFTsForOwner"
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
                    nfts.append(_transform_alchemy_to_simplehash(nft, chain_id))

                # Update next page key
                if data.page_key:
                    next_page_key = data.page_key

    return SimpleHashNFTResponse(next_cursor=next_page_key, nfts=nfts)


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
        if "error" in json_response:
            raise ValueError(f"Alchemy API error: {json_response['error']}")
        return SolanaAssetMerkleProof.model_validate(json_response["result"])


@simplehash_router.get("/nfts/owners", response_model=SimpleHashNFTResponse)
async def get_nfts_by_owner(
    wallet_addresses: list[str] = Query(
        ..., description="The wallet addresses to fetch NFTs for"
    ),
    chains: list[SimpleHashChain] = Query(
        ..., description="List of chains to fetch NFTs from"
    ),
    cursor: str | None = Query(None, description="Cursor for pagination"),
) -> SimpleHashNFTResponse:
    params = httpx.QueryParams(
        {"chains": [_simplehash_chain_to_chain_id(chain) for chain in chains]},
        owner=wallet_addresses[0],
    )

    if cursor:
        params = params.set("page_key", cursor)

    return RedirectResponse(
        url=router.url_path_for("get_nfts_by_owner") + f"?{params}", status_code=307
    )


@simplehash_router.get(
    "/nfts/proof/solana/{token_address}", response_model=SolanaAssetMerkleProof
)
async def get_compressed_nft_proof(
    token_address: str = Path(
        ..., description="The token address to fetch the proof for"
    ),
) -> SolanaAssetMerkleProof:
    return RedirectResponse(
        url=router.url_path_for("get_solana_asset_proof")
        + f"?token_address={token_address}",
        status_code=307,
    )
