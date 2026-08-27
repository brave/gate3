import asyncio
import base64
import contextlib
import json
import logging
from collections.abc import Awaitable, Iterable
from typing import NoReturn
from itertools import batched

import httpx
from fastapi import APIRouter, HTTPException, Path, Query

from app.api.common.annotations import SPAM_FILTER_DESCRIPTION
from app.api.common.models import Chain, Coin, Tags
from app.api.common.utils import is_evm_address, is_solana_address
from app.api.nft.models import (
    AlchemyNFT,
    AlchemyNFTResponse,
    AlchemyTokenType,
    NFTSpamFilter,
    SimpleHashCollection,
    SimpleHashContract,
    SimpleHashExtraMetadata,
    SimpleHashNFT,
    SimpleHashNFTResponse,
    SimpleHashOwner,
    SimpleHashTokenType,
    SolanaAsset,
    SolanaAssetMerkleProof,
    SolanaAssetOwnership,
    SolanaAssetResponse,
    SolanaOwnershipModel,
    TraitAttribute,
)
from app.config import settings
from app.core.http import create_http_client

logger = logging.getLogger(__name__)

# Alchemy rejects getNFTMetadataBatch requests with more than 100 tokens.
ALCHEMY_NFT_METADATA_BATCH_LIMIT = 100
# Largest page Alchemy's getNFTsForOwner serves. Bigger pages mean fewer billed
# calls to walk a wallet.
ALCHEMY_NFT_OWNER_PAGE_SIZE = 100
# DAS getAssetsByOwner allows up to 1000, but some wallets hold assets with
# megabytes of metadata each. A page that overruns ALCHEMY_NFT_CALL_TIMEOUT
# returns nothing at all, so keep Solana pages small enough to finish.
ALCHEMY_SOLANA_OWNER_PAGE_SIZE = 50
# Per-request bound on concurrent Alchemy calls. It caps the fan-out of a
# single large request; it does not bound the pod's total upstream
# concurrency, which Alchemy rate-limits per app.
ALCHEMY_NFT_MAX_CONCURRENT_REQUESTS = 4
# Wall-clock budget for one Alchemy call, body and transport retries included.
# httpx timeouts are per read, so a huge body that keeps trickling in never
# trips them; some DAS wallets return tens of megabytes per page.
ALCHEMY_NFT_CALL_TIMEOUT = 30.0

router = APIRouter(prefix="/api/nft", tags=[Tags.NFT])
simplehash_router = APIRouter(prefix="/simplehash/api/v0", tags=[Tags.NFT])


async def _alchemy_json(
    request: Awaitable[httpx.Response],
    *,
    chain: Chain,
    method: str,
    semaphore: asyncio.Semaphore | None = None,
) -> dict:
    """Await an Alchemy request and return its JSON body.

    Upstream failures are logged by network/method/status only and surfaced
    as 502s, so the request URL (which carries the API key) never reaches
    logs, error trackers, or clients. When a semaphore is given, the request
    is awaited while holding it, so concurrent fan-outs stay bounded. Each
    call gets ALCHEMY_NFT_CALL_TIMEOUT of wall-clock time, counted after the
    semaphore is acquired.
    """

    def fail(reason: str) -> NoReturn:
        logger.warning("Alchemy %s on %s %s", method, chain.alchemy_id, reason)
        raise HTTPException(
            status_code=502, detail="Upstream NFT provider error"
        ) from None

    try:
        async with semaphore if semaphore else contextlib.nullcontext():
            async with asyncio.timeout(ALCHEMY_NFT_CALL_TIMEOUT):
                response = await request
        response.raise_for_status()
    except TimeoutError:
        fail(f"timed out after {ALCHEMY_NFT_CALL_TIMEOUT:.0f}s")
    except httpx.HTTPStatusError as exc:
        fail(f"failed with HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        fail(f"failed: {type(exc).__name__}")
    return response.json()


# Chain mapping dictionaries
_SIMPLEHASH_TO_CHAIN = {chain.simplehash_id: chain for chain in Chain}


def _filter_chains_by_address_type(
    chains: list[Chain], wallet_address: str
) -> list[Chain]:
    if not wallet_address:
        return chains

    is_evm = is_evm_address(wallet_address)
    is_solana = is_solana_address(wallet_address)

    # If we can't determine the address type, return all chains
    if not is_evm and not is_solana:
        return chains

    filtered_chains = []
    for chain in chains:
        if is_evm and chain.coin == Coin.ETH:
            filtered_chains.append(chain)
        elif is_solana and chain.coin == Coin.SOL:
            filtered_chains.append(chain)
        else:
            # Skip chains that are not compatible with the wallet address
            continue

    return filtered_chains


def _get_spam_score_for_solana_collection(collection_name: str | None) -> int:
    if collection_name is None:
        return 0

    spam_keywords = {"airdrop", "lucky box", "reward box"}
    collection_name_lower = collection_name.lower()
    return (
        1 if any(keyword in collection_name_lower for keyword in spam_keywords) else 0
    )


def _token_type_to_simplehash(
    token_type: AlchemyTokenType | str,
) -> SimpleHashTokenType:
    if token_type == AlchemyTokenType.ERC721:
        return SimpleHashTokenType.ERC721
    elif token_type == AlchemyTokenType.ERC1155:
        return SimpleHashTokenType.ERC1155

    # TODO: Add support for these missing token types:
    #  - SimpleHashTokenType.NON_FUNGIBLE_EDITION
    #  - SimpleHashTokenType.PROGRAMMABLE_NON_FUNGIBLE

    return SimpleHashTokenType.UNKNOWN


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
        # Alchemy's EVM metadata carries no ownership
        owners=None,
    )


def _solana_owners(
    ownership: SolanaAssetOwnership | None,
) -> list[SimpleHashOwner] | None:
    """Current holders of a Solana asset, in the SimpleHash owners shape.

    DAS names one owner for the "single" ownership model. Other models
    (token editions) carry no per-holder amounts, so holders are unknown
    and the result is None, which consumers treat as "skip" rather than 0.
    """
    if (
        ownership
        and ownership.ownership_model == SolanaOwnershipModel.SINGLE
        and ownership.owner
    ):
        return [SimpleHashOwner(owner_address=ownership.owner, quantity=1)]
    return None


def _transform_solana_asset_to_simplehash(asset: SolanaAsset) -> SimpleHashNFT:
    # Skip burnt NFTs or assets without content
    if asset.burnt or not asset.content or not asset.content.metadata:
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
    if asset.content.links and asset.content.links.image:
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

    return SimpleHashNFT(
        chain=Chain.SOLANA.simplehash_id,
        contract_address=asset.id,
        token_id=None,
        name=name,
        description=description,
        image_url=image_url,
        background_color=None,
        external_url=asset.content.links.external_url if asset.content.links else None,
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
            image_original_url=image_url,
            animation_original_url=None,
            metadata_original_url=asset.content.json_uri,
        ),
        owners=_solana_owners(asset.ownership),
    )


async def _solana_rpc(
    client: httpx.AsyncClient,
    method: str,
    params: dict | list,
    *,
    semaphore: asyncio.Semaphore | None = None,
) -> dict | list:
    """Call a Solana DAS JSON-RPC method on Alchemy and return its result."""
    url = (
        f"https://{Chain.SOLANA.alchemy_id}.g.alchemy.com/v2/{settings.ALCHEMY_API_KEY}"
    )
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    json_response = await _alchemy_json(
        client.post(url, json=body),
        chain=Chain.SOLANA,
        method=method,
        semaphore=semaphore,
    )
    if error := json_response.get("error"):
        # Same treatment as an HTTP failure; the body carries no secrets
        logger.warning("Alchemy %s on solana-mainnet returned error %s", method, error)
        raise HTTPException(status_code=502, detail="Upstream NFT provider error")
    return json_response["result"]


def _transform_solana_assets(assets: Iterable[SolanaAsset]) -> list[SimpleHashNFT]:
    return [
        nft for asset in assets if (nft := _transform_solana_asset_to_simplehash(asset))
    ]


def _encode_owner_cursor(page_keys: dict[Chain, str | int]) -> str | None:
    """Pack each chain's page key into one opaque cursor, keyed by network id.

    Returns None when no chain has a further page, which ends pagination.
    """
    if not page_keys:
        return None
    by_network = {chain.alchemy_id: key for chain, key in page_keys.items()}
    raw = json.dumps(by_network, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_owner_cursor(cursor: str) -> dict[str, str | int] | None:
    """Unpack a cursor produced by _encode_owner_cursor, or None if it is not one."""
    padded = cursor + "=" * (-len(cursor) % 4)  # tolerate stripped padding
    try:
        page_keys = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except ValueError:  # includes binascii.Error and JSONDecodeError
        return None
    if not isinstance(page_keys, dict):
        return None
    return page_keys


def _resolve_owner_page_keys(
    cursor: str | None, requested_chains: list[Chain]
) -> dict[Chain, str | int | None]:
    """Decide which chains an owner lookup queries, and with which page key.

    A fresh lookup queries every requested chain from its first page. A
    cursor from a previous response narrows that to the chains that still
    have pages, each with its own key: an Alchemy pageKey for EVM chains and
    a 1-based page number for Solana.
    """
    if cursor is None:
        return dict.fromkeys(requested_chains)

    decoded = _decode_owner_cursor(cursor)
    if decoded is None:
        # A raw Alchemy page key from before per-chain cursors: apply it to
        # every EVM chain as the old shared cursor did. Solana pages are
        # integers, so it cannot apply there. Drop once no client can still
        # hold a cursor issued before this shipped.
        return {chain: cursor for chain in requested_chains if chain != Chain.SOLANA}

    page_keys: dict[Chain, str | int | None] = {}
    for chain in requested_chains:
        if chain.alchemy_id not in decoded:
            continue
        key = decoded[chain.alchemy_id]
        try:
            page_keys[chain] = int(key) if chain == Chain.SOLANA else str(key)
        except TypeError, ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor") from None
    return page_keys


async def _get_solana_assets_by_owner(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    wallet_address: str,
    page_key: str | int | None,
    page_size: int,
) -> tuple[list[SimpleHashNFT], int | None]:
    """Fetch one page of a wallet's Solana assets via Alchemy's DAS getAssetsByOwner.

    DAS pages are 1-based integers; a full page means there may be another.
    """
    page = int(page_key) if page_key else 1
    params = {
        "ownerAddress": wallet_address,
        "page": page,
        "limit": page_size,
        "options": {
            "showUnverifiedCollections": False,
            "showCollectionMetadata": True,
        },
    }
    result = await _solana_rpc(client, "getAssetsByOwner", params, semaphore=semaphore)
    solana_response = SolanaAssetResponse.model_validate(result)
    nfts = _transform_solana_assets(solana_response.items)
    next_page = page + 1 if len(solana_response.items) >= page_size else None
    return nfts, next_page


async def _get_nfts_for_owner(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    chain: Chain,
    wallet_address: str,
    page_key: str | int | None,
    page_size: int,
    exclude_spam: bool,
) -> tuple[list[SimpleHashNFT], str | None]:
    """Fetch one page of a wallet's NFTs on an EVM chain via Alchemy's getNFTsForOwner.

    With exclude_spam, Alchemy drops spam upstream so the page never carries it.
    """
    url = f"https://{chain.alchemy_id}.g.alchemy.com/nft/v3/{settings.ALCHEMY_API_KEY}/getNFTsForOwner"
    params = httpx.QueryParams(
        owner=wallet_address,
        pageSize=page_size,
        withMetadata=True,
    )
    if page_key:
        params = params.set("pageKey", str(page_key))
    if exclude_spam:
        params = params.set("excludeFilters[]", "SPAM")

    json_response = await _alchemy_json(
        client.get(url, params=params),
        chain=chain,
        method="getNFTsForOwner",
        semaphore=semaphore,
    )
    data = AlchemyNFTResponse.model_validate(json_response)

    nfts = [_transform_alchemy_to_simplehash(nft, chain) for nft in data.owned_nfts]
    return nfts, data.page_key


@router.get("/v1/getNFTsForOwner", response_model=SimpleHashNFTResponse)
async def get_nfts_by_owner(
    wallet_address: str = Query(
        ..., description="The wallet address to fetch NFTs for"
    ),
    chains: list[str] = Query(
        ..., description="List of chains to fetch NFTs from in format coin.chain_id"
    ),
    page_key: str | None = Query(
        None, description="Cursor from a previous response, to fetch the next page"
    ),
    page_size: int = Query(
        ALCHEMY_NFT_OWNER_PAGE_SIZE, description="Number of NFTs to fetch per page"
    ),
    spam: NFTSpamFilter = Query(NFTSpamFilter.ALL, description=SPAM_FILTER_DESCRIPTION),
) -> SimpleHashNFTResponse:
    """
    Fetch NFTs owned by a wallet address across multiple chains using Alchemy API.
    The response is transformed to match the SimpleHash API format.
    """
    if not settings.ALCHEMY_API_KEY:
        raise ValueError("ALCHEMY_API_KEY is not configured")

    requested_chains = []
    for chain_str in chains:
        coin, chain_id = chain_str.split(".")
        chain = Chain.get(coin, chain_id)
        if chain and chain.has_nft_support:
            requested_chains.append(chain)

    # Each chain paginates on its own; a cursor narrows the lookup to the
    # chains that still have pages
    page_keys = _resolve_owner_page_keys(page_key, requested_chains)

    # Fetch every chain's page concurrently; gather keeps request order
    async with create_http_client() as client:
        semaphore = asyncio.Semaphore(ALCHEMY_NFT_MAX_CONCURRENT_REQUESTS)
        fetches = []
        for chain, chain_page_key in page_keys.items():
            if chain == Chain.SOLANA:
                fetch = _get_solana_assets_by_owner(
                    client,
                    semaphore,
                    wallet_address,
                    chain_page_key,
                    min(page_size, ALCHEMY_SOLANA_OWNER_PAGE_SIZE),
                )
            else:
                fetch = _get_nfts_for_owner(
                    client,
                    semaphore,
                    chain,
                    wallet_address,
                    chain_page_key,
                    page_size,
                    spam == NFTSpamFilter.EXCLUDE,
                )
            fetches.append(fetch)
        results = await asyncio.gather(*fetches, return_exceptions=True)

    pages = _skip_failed_chains(page_keys, results)
    nfts = [nft for chain_nfts, _ in pages.values() for nft in chain_nfts]
    if spam != NFTSpamFilter.ALL:
        # Filter on gate3's own verdict: Solana spam is a gate3 heuristic, and
        # Alchemy's documented includeFilters[]=SPAM returned unfiltered pages
        # when tried, so "only spam" cannot be pushed upstream either.
        keep_spam = spam == NFTSpamFilter.ONLY
        nfts = [nft for nft in nfts if bool(nft.collection.spam_score) == keep_spam]
    next_page_keys = {chain: key for chain, (_, key) in pages.items() if key}
    return SimpleHashNFTResponse(
        next_cursor=_encode_owner_cursor(next_page_keys), nfts=nfts
    )


def _skip_failed_chains[P](
    chains: Iterable[Chain], results: list[P | BaseException]
) -> dict[Chain, P]:
    """Keep the chains whose page fetch succeeded, in request order.

    A chain that failed upstream (an HTTPException, already logged where
    it happened) is left out of the response and of the cursor, so one bad
    chain does not sink the whole lookup. Only if every chain failed is the
    first failure surfaced. Anything else is re-raised.
    """
    pages: dict[Chain, P] = {}
    failures: list[BaseException] = []
    for chain, result in zip(chains, results):
        if isinstance(result, HTTPException):
            failures.append(result)
        elif isinstance(result, BaseException):
            raise result
        else:
            pages[chain] = result
    if failures and not pages:
        raise failures[0]
    return pages


async def _get_solana_assets(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, asset_ids: list[str]
) -> list[SimpleHashNFT]:
    """Fetch and transform Solana assets by id via Alchemy's DAS getAssets."""
    result = await _solana_rpc(
        client, "getAssets", {"ids": asset_ids}, semaphore=semaphore
    )
    # Unknown ids come back as null entries
    return _transform_solana_assets(
        SolanaAsset.model_validate(nft_data) for nft_data in result if nft_data
    )


async def _get_nft_metadata_batch(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    chain: Chain,
    batch: Iterable[tuple[str, str]],
) -> list[SimpleHashNFT]:
    """Fetch and transform one getNFTMetadataBatch request for a chain.

    `batch` must hold at most ALCHEMY_NFT_METADATA_BATCH_LIMIT tokens.
    """
    url = f"https://{chain.alchemy_id}.g.alchemy.com/nft/v3/{settings.ALCHEMY_API_KEY}/getNFTMetadataBatch"
    tokens = [
        {"contractAddress": contract_address, "tokenId": token_id}
        for contract_address, token_id in batch
    ]
    json_response = await _alchemy_json(
        client.post(url, json={"tokens": tokens}),
        chain=chain,
        method="getNFTMetadataBatch",
        semaphore=semaphore,
    )
    return [
        _transform_alchemy_to_simplehash(AlchemyNFT.model_validate(nft_data), chain)
        for nft_data in json_response["nfts"]
        if nft_data
    ]


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

    solana_nfts = []
    other_nfts = []

    # Separate Solana and other chain NFTs
    for nft_id in nft_ids_list:
        # Skip empty strings from trailing commas
        if not nft_id.strip():
            continue

        parts = [part.strip() for part in nft_id.split(".") if part.strip()]

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

    # If no valid NFT IDs were found, return empty response
    if not solana_nfts and not other_nfts:
        return SimpleHashNFTResponse(next_cursor=None, nfts=[])

    # Group EVM NFTs by chain
    chain_nfts: dict[Chain, list[tuple[str, str]]] = {}
    for nft_id in other_nfts:
        parts = [part.strip() for part in nft_id.split(".") if part.strip()]

        # Skip malformed EVM IDs that don't have exactly 4 parts
        if len(parts) != 4:
            continue

        coin, chain_id, contract_address, token_id = parts

        chain = Chain.get(coin, chain_id)
        if not chain:
            continue

        chain_nfts.setdefault(chain, []).append((contract_address, token_id))

    # Fetch Solana assets and each chain's metadata batches concurrently.
    # gather preserves input order: Solana first, then chains in request order.
    async with create_http_client() as client:
        semaphore = asyncio.Semaphore(ALCHEMY_NFT_MAX_CONCURRENT_REQUESTS)
        fetches = []
        if solana_nfts:
            fetches.append(_get_solana_assets(client, semaphore, solana_nfts))
        fetches.extend(
            _get_nft_metadata_batch(client, semaphore, chain, batch)
            for chain, nft_list in chain_nfts.items()
            for batch in batched(nft_list, ALCHEMY_NFT_METADATA_BATCH_LIMIT)
        )
        results = await asyncio.gather(*fetches)

    nfts = [nft for result in results for nft in result]
    return SimpleHashNFTResponse(next_cursor=None, nfts=nfts)


@router.get("/v1/getSolanaAssetProof", response_model=SolanaAssetMerkleProof)
async def get_solana_asset_proof(
    token_address: str = Query(
        ..., description="The token address to fetch the proof for"
    ),
) -> SolanaAssetMerkleProof:
    async with create_http_client() as client:
        result = await _solana_rpc(client, "getAssetProof", [token_address])
    return SolanaAssetMerkleProof.model_validate(result)


@simplehash_router.get("/nfts/owners", response_model=SimpleHashNFTResponse)
async def get_simplehash_nfts_by_owner(
    wallet_addresses: list[str] = Query(
        ..., description="The wallet addresses to fetch NFTs for"
    ),
    chains: list[str] | None = Query(
        ..., description="List of chains to fetch NFTs from"
    ),
    cursor: str | None = Query(None, description="Cursor for pagination"),
    spam: NFTSpamFilter = Query(NFTSpamFilter.ALL, description=SPAM_FILTER_DESCRIPTION),
) -> SimpleHashNFTResponse:
    filtered_chains = {
        chain_str for chain_raw in (chains or []) for chain_str in chain_raw.split(",")
    }

    internal_chains = [
        chain
        for chain_str in filtered_chains
        if (chain := _SIMPLEHASH_TO_CHAIN.get(chain_str))
    ]

    wallet_address = wallet_addresses[0] if wallet_addresses else ""
    compatible_chains = _filter_chains_by_address_type(internal_chains, wallet_address)

    internal_chains_ids = [
        f"{chain.coin.value.lower()}.{chain.chain_id}" for chain in compatible_chains
    ]

    # Call the internal function directly instead of redirecting
    return await get_nfts_by_owner(
        wallet_address=wallet_address,
        chains=internal_chains_ids,
        page_key=cursor,
        page_size=ALCHEMY_NFT_OWNER_PAGE_SIZE,
        spam=spam,
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

        parts = [part.strip() for part in nft_id.split(".") if part.strip()]

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

    # If no valid NFT IDs were found, return empty response
    if not internal_nft_ids:
        return SimpleHashNFTResponse(next_cursor=None, nfts=[])

    # Call the internal function directly instead of redirecting
    return await get_nfts_by_ids(ids=",".join(internal_nft_ids))
