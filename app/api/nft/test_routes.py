import asyncio
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.common.models import Chain
from app.api.nft.models import (
    SimpleHashNFTResponse,
    SolanaAssetContentLink,
    SolanaAssetMerkleProof,
)
from app.api.nft.routes import _decode_owner_cursor, _encode_owner_cursor
from app.main import app

client = TestClient(app)

# Mock constants
MOCK_EVM_WALLET_ADDRESS = "0x1234567890123456789012345678901234567890"
MOCK_SOLANA_WALLET_ADDRESS = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
MOCK_EVM_CONTRACT_ADDRESS = "0xabcdef1234567890abcdef1234567890abcdef12"
MOCK_EVM_TOKEN_ID = "123"
MOCK_SPL_TOKEN_MINT_ADDRESS = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"

MOCK_NFT_ALCHEMY_RESPONSE = {
    "contract": {
        "address": "0x123",
        "name": "MockNFT",
        "symbol": "MOCK",
        "totalSupply": "1000",
        "tokenType": "ERC721",
        "contractDeployer": "0x456",
        "deployedBlockNumber": 123456,
        "openSeaMetadata": {
            "floorPrice": 0.1,
            "collectionName": "Mock Collection",
            "safelistRequestStatus": "verified",
            "imageUrl": "https://example.com/image.jpg",
            "description": "A mock NFT collection",
            "externalUrl": "https://example.com",
            "twitterUsername": "mocknft",
            "discordUrl": "https://discord.gg/mock",
            "lastIngestedAt": "2023-01-01T00:00:00.000Z",
        },
        "isSpam": None,
        "spamClassifications": [],
    },
    "tokenId": "1",
    "tokenType": "ERC721",
    "name": "Mock NFT #1",
    "description": "A mock NFT description",
    "image": {
        "cachedUrl": "https://example.com/cached.jpg",
        "thumbnailUrl": "https://example.com/thumb.jpg",
        "pngUrl": "https://example.com/image.png",
        "contentType": "image/png",
        "size": 1000000,
        "originalUrl": "https://example.com/original.jpg",
    },
    "raw": {
        "tokenUri": "https://example.com/metadata/1",
        "metadata": {
            "name": "Mock NFT #1",
            "description": "A mock NFT description",
            "image": "https://example.com/image.jpg",
            "external_url": "https://example.com",
            "attributes": [
                {"value": "Red", "trait_type": "Color"},
                {"value": "Round", "trait_type": "Shape"},
            ],
        },
        "error": None,
    },
    "tokenUri": "https://example.com/metadata/1",
    "timeLastUpdated": "2023-01-01T00:00:00.000Z",
    "balance": "1",
}

MOCK_SOLANA_ASSET_RESPONSE = {
    "id": "mint123",
    "interface": "ProgrammableNFT",
    "content": {
        "metadata": {
            "name": "Mock Solana NFT",
            "symbol": "MSN",
            "description": "A mock Solana NFT",
            "attributes": [],
        },
        "links": {
            "image": "https://example.com/solana-image.jpg",
            "external_url": "https://example.com",
        },
        "json_uri": "https://example.com/metadata/solana.json",
    },
    "grouping": [],
    "ownership": {
        "ownership_model": "single",
        "owner": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
    },
    "mutable": False,
    "burnt": False,
}


@pytest.fixture
def mock_settings(monkeypatch):
    mock = MagicMock()
    mock.ALCHEMY_API_KEY = "test_key"
    mock.SIMPLEHASH_API_KEY = "test_key"
    monkeypatch.setattr("app.api.nft.routes.settings", mock)
    return mock


@pytest.fixture
def mock_httpx_client(monkeypatch):
    mock_client = AsyncMock()

    # Create mock response objects that return actual values, not coroutines
    mock_get_response = Mock()
    mock_post_response = Mock()

    # Set up the mock responses to return actual values, not coroutines
    mock_get_response.status_code = 200
    mock_get_response.json.return_value = {}
    mock_get_response.raise_for_status.return_value = None

    mock_post_response.status_code = 200
    mock_post_response.json.return_value = {}
    mock_post_response.raise_for_status.return_value = None

    # Configure the client methods
    mock_client.get.return_value = mock_get_response
    mock_client.post.return_value = mock_post_response

    # Create a mock context manager
    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_client
    mock_context.__aexit__.return_value = None

    # Mock create_http_client to return our mock context manager
    monkeypatch.setattr(
        "app.api.nft.routes.create_http_client", lambda **kwargs: mock_context
    )

    return mock_client


def _create_mock_response(status_code=200, json_data=None):
    mock_response_obj = Mock()
    mock_response_obj.status_code = status_code
    mock_response_obj.raise_for_status.return_value = None
    if json_data is not None:
        mock_response_obj.json.return_value = json_data
    return mock_response_obj


def _create_mock_post_side_effect(
    mock_evm_response, mock_solana_response, capture_requests=None
):
    def f(*args, **kwargs):
        if (
            capture_requests is not None
            and "json" in kwargs
            and "tokens" in kwargs["json"]
        ):
            capture_requests.append(kwargs["json"]["tokens"])

        if "solana-mainnet.g.alchemy.com" in args[0]:
            return _create_mock_response(json_data=mock_solana_response)
        else:
            return _create_mock_response(json_data=mock_evm_response)

    return f


def _create_mock_get_side_effect(mock_evm_response):
    def f(*args, **kwargs):
        return _create_mock_response(json_data=mock_evm_response)

    return f


def test_get_nfts_by_owner(mock_httpx_client, mock_settings):
    mock_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_httpx_client.get.return_value = AsyncMock(
        status_code=200,
        json=Mock(return_value=mock_response),
        raise_for_status=Mock(return_value=None),
    )

    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1"
    )
    assert response.status_code == 200
    data = response.json()

    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1
    nft = sh_response.nfts[0]
    assert nft.chain == "ethereum"
    assert nft.contract_address == "0x123"
    assert nft.token_id == "1"
    assert nft.name == "Mock NFT #1"
    assert nft.description == "A mock NFT description"
    assert nft.image_url == "https://example.com/cached.jpg"
    assert nft.background_color is None
    assert nft.external_url is None
    assert nft.contract.type == "ERC721"
    assert nft.contract.name == "MockNFT"
    assert nft.contract.symbol == "MOCK"
    assert nft.collection.name == "MockNFT"
    assert nft.collection.spam_score == 0
    attributes = nft.extra_metadata.attributes
    assert len(attributes) == 2
    assert attributes[0].trait_type == "Color"
    assert attributes[0].value == "Red"
    assert attributes[1].trait_type == "Shape"
    assert attributes[1].value == "Round"


def test_get_nfts_by_owner_invalid_chain(mock_settings):
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x999"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["nfts"]) == 0


def test_get_nfts_by_owner_missing_api_key(mock_settings):
    # Override settings to simulate missing API key
    mock_settings.ALCHEMY_API_KEY = None

    with pytest.raises(ValueError):
        client.get("/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1")


def test_get_solana_asset_proof(mock_httpx_client, mock_settings):
    mock_response = {
        "result": {
            "proof": ["hash1", "hash2", "hash3"],
            "root": "root_hash",
            "tree_id": "tree_123",
            "node_index": 42,
            "leaf": "leaf_hash",
            "status": "finalized",
        },
        "error": None,
    }

    mock_httpx_client.post.return_value = AsyncMock(
        status_code=200,
        json=Mock(return_value=mock_response),
        raise_for_status=Mock(return_value=None),
    )

    response = client.get("/api/nft/v1/getSolanaAssetProof?token_address=mint123")
    assert response.status_code == 200
    data = response.json()
    sh_response = SolanaAssetMerkleProof.model_validate(data)
    assert sh_response.root == "root_hash"
    assert sh_response.tree_id == "tree_123"
    assert sh_response.node_index == 42
    assert sh_response.leaf == "leaf_hash"
    assert sh_response.proof == ["hash1", "hash2", "hash3"]


def test_get_solana_asset_proof_error(mock_httpx_client, mock_settings, caplog):
    mock_response = {
        "error": "Token not found",
    }
    mock_httpx_client.post.return_value = AsyncMock(
        status_code=200,
        json=Mock(return_value=mock_response),
        raise_for_status=Mock(return_value=None),
    )

    with caplog.at_level("WARNING"):
        response = client.get(
            "/api/nft/v1/getSolanaAssetProof?token_address=invalid_token"
        )

    # A JSON-RPC error is an upstream failure like any other
    assert response.status_code == 502
    assert "Alchemy getAssetProof on solana-mainnet returned error" in caplog.text
    assert "test_key" not in caplog.text


def test_get_simplehash_nfts_by_owner(mock_httpx_client, mock_settings):
    mock_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    # Configure the mock response
    mock_httpx_client.get.return_value.json.return_value = mock_response

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=0x123&chains=ethereum"
    )
    assert response.status_code == 200
    data = response.json()

    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1
    nft = sh_response.nfts[0]
    assert nft.chain == "ethereum"
    assert nft.contract_address == "0x123"
    assert nft.token_id == "1"
    assert nft.name == "Mock NFT #1"
    assert nft.description == "A mock NFT description"
    assert nft.image_url == "https://example.com/cached.jpg"
    assert nft.background_color is None
    assert nft.external_url is None
    assert nft.contract.type == "ERC721"
    assert nft.contract.name == "MockNFT"
    assert nft.contract.symbol == "MOCK"
    assert nft.collection.name == "MockNFT"
    assert nft.collection.spam_score == 0
    attributes = nft.extra_metadata.attributes
    assert len(attributes) == 2
    assert attributes[0].trait_type == "Color"
    assert attributes[0].value == "Red"
    assert attributes[1].trait_type == "Shape"
    assert attributes[1].value == "Round"


def test_get_simplehash_nfts_by_owner_multiple_chains(mock_httpx_client, mock_settings):
    mock_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_httpx_client.get.return_value.json.return_value = mock_response

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=0x123&chains=ethereum,polygon"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    # Should get 2 NFTs - one from Ethereum and one from Polygon
    assert len(sh_response.nfts) == 2


def test_get_simplehash_nfts_by_owner_with_cursor(mock_httpx_client, mock_settings):
    mock_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": "next_page_key",
    }

    mock_httpx_client.get.return_value.json.return_value = mock_response

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=0x123&chains=ethereum&cursor=page123"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1
    assert sh_response.next_cursor is not None
    assert _decode_owner_cursor(sh_response.next_cursor) == {
        "eth-mainnet": "next_page_key"
    }


def test_get_simplehash_compressed_nft_proof(mock_httpx_client, mock_settings):
    mock_response = {
        "result": {
            "proof": ["hash1", "hash2", "hash3"],
            "root": "root_hash",
            "tree_id": "tree_123",
            "node_index": 42,
            "leaf": "leaf_hash",
            "status": "finalized",
        },
        "error": None,
    }

    mock_httpx_client.post.return_value.json.return_value = mock_response

    response = client.get("/simplehash/api/v0/nfts/proof/solana/mint123")
    assert response.status_code == 200
    data = response.json()
    sh_response = SolanaAssetMerkleProof.model_validate(data)
    assert sh_response.root == "root_hash"
    assert sh_response.tree_id == "tree_123"
    assert sh_response.node_index == 42
    assert sh_response.leaf == "leaf_hash"
    assert sh_response.proof == ["hash1", "hash2", "hash3"]


def test_get_simplehash_nfts_by_ids_solana(mock_httpx_client, mock_settings):
    mock_response = {
        "result": [MOCK_SOLANA_ASSET_RESPONSE],
    }

    mock_httpx_client.post.return_value.json.return_value = mock_response

    response = client.get(
        f"/simplehash/api/v0/nfts/assets?nft_ids=solana.{MOCK_SPL_TOKEN_MINT_ADDRESS}"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1


def test_get_simplehash_nfts_by_ids_solana_without_metadata_name(
    mock_httpx_client, mock_settings
):
    # Sentry GATE3-3P: DAS returns content.metadata as {} for some assets
    nameless: dict[str, Any] = copy.deepcopy(MOCK_SOLANA_ASSET_RESPONSE)
    nameless["content"]["metadata"] = {}
    mock_httpx_client.post.return_value.json.return_value = {"result": [nameless]}

    response = client.get(
        f"/simplehash/api/v0/nfts/assets?nft_ids=solana.{MOCK_SPL_TOKEN_MINT_ADDRESS}"
    )
    assert response.status_code == 200
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert len(sh_response.nfts) == 1
    assert sh_response.nfts[0].name is None


def test_get_simplehash_nfts_by_ids_skips_non_base58_solana_ids(
    mock_httpx_client, mock_settings
):
    # Sentry GATE3-3Q: Alchemy rejects the whole getAssets batch with
    # "Pubkey Validation Err" when any id is not a base58 pubkey
    bad_id = (
        "0x1668E0FB0Dd39e54fE33f80a9F37c4dBF172E1b"
        "0x1668E0FB0Dd39e54fE33f80a9F37c4dBF172E1b11"
    )
    mock_httpx_client.post.return_value.json.return_value = {
        "result": [MOCK_SOLANA_ASSET_RESPONSE]
    }

    response = client.get(f"/simplehash/api/v0/nfts/assets?nft_ids=solana.{bad_id}")
    assert response.status_code == 200
    assert response.json()["nfts"] == []
    mock_httpx_client.post.assert_not_called()

    response = client.get(
        "/simplehash/api/v0/nfts/assets"
        f"?nft_ids=solana.{bad_id},solana.{MOCK_SPL_TOKEN_MINT_ADDRESS}"
    )
    assert response.status_code == 200
    assert len(response.json()["nfts"]) == 1
    assert mock_httpx_client.post.call_args.kwargs["json"]["params"] == {
        "ids": [MOCK_SPL_TOKEN_MINT_ADDRESS]
    }


def test_get_simplehash_nfts_by_ids(mock_httpx_client, mock_settings):
    # EVM NFTs carry no ownership; brave-core skips a null owners list
    mock_response = {
        "nfts": [MOCK_NFT_ALCHEMY_RESPONSE],
    }

    mock_httpx_client.post.return_value.json.return_value = mock_response

    response = client.get(
        "/simplehash/api/v0/nfts/assets?nft_ids=ethereum.0x123.456,polygon.0x789.101112"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    # Should get 2 NFTs - one from Ethereum and one from Polygon
    assert len(sh_response.nfts) == 2
    assert all(nft.owners is None for nft in sh_response.nfts)


def test_get_simplehash_nfts_by_ids_handles_invalid_input(
    mock_httpx_client, mock_settings
):
    # Ref: https://github.com/brave/gate3/issues/97
    response = client.get(
        "/simplehash/api/v0/nfts/assets?nft_ids=solana.,ethereum..123,ethereum.0x123.,invalid.chain.123"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    # Should return empty response since all IDs are invalid
    assert len(sh_response.nfts) == 0
    assert sh_response.next_cursor is None


def test_get_nfts_by_ids_handles_malformed_input_gracefully(
    mock_httpx_client, mock_settings
):
    """
    Test that verifies malformed NFT IDs are gracefully skipped.
    """
    mock_response = {
        "nfts": [MOCK_NFT_ALCHEMY_RESPONSE, MOCK_NFT_ALCHEMY_RESPONSE],
    }

    # Mock Solana response
    mock_solana_response = {
        "result": [MOCK_SOLANA_ASSET_RESPONSE],
    }

    captured_requests = []
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        mock_response, mock_solana_response, captured_requests
    )

    # Test with various malformed inputs that should be gracefully handled:
    # - Valid EVM ID: eth.0x1.0x123.456
    # - Valid EVM ID with trailing comma: eth.0x1.0x789.101112, (should be processed as valid)
    # - Missing token_id: eth.0x1.0xabc. (should be skipped)
    # - Empty string: (empty) (should be skipped)
    # - Invalid chain ID: eth.0x999.0xinvalid (should be skipped)
    # - Valid Solana ID: sol.0x65.<mint> (should be processed as valid)
    # - Malformed Solana ID: sol.0x65. (missing address, should be skipped)
    # - Malformed Solana ID: sol.0x65.<mint>.extra (too many parts, should be skipped)
    # - Invalid Solana chain ID: sol.0x999.<mint> (invalid chain ID, should be skipped)
    # - Non-base58 Solana address: sol.0x65.0xdef123 (should be skipped)
    mint = MOCK_SPL_TOKEN_MINT_ADDRESS
    response = client.get(
        "/api/nft/v1/getNFTsByIds?ids="
        "eth.0x1.0x123.456,"
        "eth.0x1.0x789.101112,"
        "eth.0x1.0xabc.,"
        "eth.0x999.0xinvalid,"
        f"sol.0x65.{mint},"
        "sol.0x65.,"
        f"sol.0x65.{mint}.extra,"
        f"sol.0x999.{mint},"
        "sol.0x65.0xdef123"
    )

    # Should not crash - should return 200 with valid NFTs
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    # Should only process the valid NFT IDs (2 EVM + 1 Solana = 3 valid ones)
    assert len(sh_response.nfts) == 3

    # Verify that we captured exactly one request with the correct tokens
    assert len(captured_requests) == 1
    assert captured_requests[0] == [
        {"contractAddress": "0x123", "tokenId": "456"},
        {"contractAddress": "0x789", "tokenId": "101112"},
    ]


def test_solana_asset_content_link_image_validation():
    # Test with boolean value - should convert to None
    # Ref: https://github.com/brave/gate3/issues/72
    link_false = SolanaAssetContentLink.model_validate({"image": False})
    assert link_false.image is None

    # Test with None - should remain None
    link_none = SolanaAssetContentLink.model_validate({"image": None})
    assert link_none.image is None

    # Test with empty string - should convert to None
    link_empty = SolanaAssetContentLink.model_validate({"image": ""})
    assert link_empty.image is None

    # Test with valid string - should apply URL validation
    # Trailing slash and whitespaces should be stripped
    link_string = SolanaAssetContentLink.model_validate(
        {"image": "https://example.com/image.jpg/   "}
    )
    assert link_string.image == "https://example.com/image.jpg"


def test_alchemy_nft_with_dict_attributes(mock_httpx_client, mock_settings):
    # Mock NFT data with dict format attributes
    mock_nft_with_dict_attributes = {
        "contract": {
            "address": "0x123",
            "name": "MockNFT",
            "symbol": "MOCK",
            "isSpam": None,
            "spamClassifications": [],
        },
        "tokenId": "1",
        "tokenType": "ERC721",
        "name": "Mock NFT #1",
        "description": "A mock NFT description",
        "image": {
            "cachedUrl": "https://example.com/cached.jpg",
            "thumbnailUrl": "https://example.com/thumb.jpg",
            "pngUrl": "https://example.com/image.png",
            "contentType": "image/png",
            "size": 1000000,
            "originalUrl": "https://example.com/original.jpg",
        },
        "raw": {
            "tokenUri": "https://example.com/metadata/1",
            "metadata": {
                "name": "Mock NFT #1",
                "description": "A mock NFT description",
                "image": "https://example.com/image.jpg",
                "external_url": "https://example.com",
                # This is a problematic format - dict instead of list
                "attributes": {
                    "Color": "Red",
                    "Shape": "Round",
                    "minter_address": "0xf30...name",
                    "name": "The Paint Room",
                },
            },
            "error": None,
        },
        "tokenUri": "https://example.com/metadata/1",
    }

    mock_response = {
        "nfts": [mock_nft_with_dict_attributes],
    }

    mock_httpx_client.post.return_value.json.return_value = mock_response

    # This should not raise a ValidationError anymore
    response = client.get("/api/nft/v1/getNFTsByIds?ids=eth.0x1.0x123.1")
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1

    # Verify the attributes are empty when metadata is not a list
    nft = sh_response.nfts[0]
    attributes = nft.extra_metadata.attributes
    assert len(attributes) == 0  # Should be empty when attributes is not a list


def test_alchemy_nft_with_string_metadata(mock_httpx_client, mock_settings):
    # Mock NFT data with string metadata
    mock_nft_with_string_metadata = {
        "contract": {
            "address": "0x123",
            "name": "MockNFT",
            "symbol": "MOCK",
            "isSpam": None,
            "spamClassifications": [],
        },
        "tokenId": "1",
        "tokenType": "ERC721",
        "name": "Mock NFT #1",
        "description": "A mock NFT description",
        "image": {
            "cachedUrl": "https://example.com/cached.jpg",
            "thumbnailUrl": "https://example.com/thumb.jpg",
            "pngUrl": "https://example.com/image.png",
            "contentType": "image/png",
            "size": 1000000,
            "originalUrl": "https://example.com/original.jpg",
        },
        "raw": {
            "tokenUri": "https://example.com/metadata/1",
            "metadata": "https://example.com/metadata/1",  # String instead of dict
            "error": None,
        },
        "tokenUri": "https://example.com/metadata/1",
    }

    mock_response = {
        "nfts": [mock_nft_with_string_metadata],
    }

    mock_httpx_client.post.return_value.json.return_value = mock_response

    response = client.get("/api/nft/v1/getNFTsByIds?ids=eth.0x1.0x123.1")
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1

    nft = sh_response.nfts[0]
    attributes = nft.extra_metadata.attributes
    assert len(attributes) == 0  # Should be empty when metadata is a string


def test_get_nfts_by_ids_handles_none_values_in_response(
    mock_httpx_client, mock_settings
):
    # Mock response with None values mixed in
    mock_solana_response = {
        "result": [MOCK_SOLANA_ASSET_RESPONSE, None],
    }

    # Mock EVM response with None values mixed in
    mock_evm_response = {
        "nfts": [None, MOCK_NFT_ALCHEMY_RESPONSE],
    }

    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        mock_evm_response, mock_solana_response
    )

    response = client.get(
        f"/simplehash/api/v0/nfts/assets?nft_ids=solana.{MOCK_SPL_TOKEN_MINT_ADDRESS},ethereum.0x123.456"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    # Should get 2 NFTs total (1 from Solana + 1 from Ethereum), None values should be skipped
    assert len(sh_response.nfts) == 2


def test_get_simplehash_nfts_by_owner_evm_wallet_filtering(
    mock_httpx_client, mock_settings
):
    mock_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_httpx_client.get.return_value.json.return_value = mock_response

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=0x1234567890123456789012345678901234567890&chains=ethereum,polygon,solana"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    # Should get 2 NFTs total (1 from Solana + 1 from Ethereum), None values should be skipped
    assert len(sh_response.nfts) == 2


def test_get_simplehash_nfts_by_owner_solana_wallet_filtering(
    mock_httpx_client, mock_settings
):
    mock_solana_response = {
        "result": {"items": [MOCK_SOLANA_ASSET_RESPONSE], "total": 1, "limit": 50}
    }

    mock_evm_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        mock_evm_response, mock_solana_response
    )
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(mock_evm_response)

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin&chains=ethereum,polygon,solana"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    assert len(sh_response.nfts) == 1


def test_get_simplehash_nfts_by_owner_unknown_wallet_filtering(
    mock_httpx_client, mock_settings
):
    mock_evm_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_solana_response = {
        "result": {"items": [MOCK_SOLANA_ASSET_RESPONSE], "total": 1, "limit": 50}
    }

    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        mock_evm_response, mock_solana_response
    )
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(mock_evm_response)

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=unknown_address_format&chains=ethereum,polygon,solana"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    assert len(sh_response.nfts) == 3


def test_get_simplehash_nfts_by_owner_empty_wallet_filtering(
    mock_httpx_client, mock_settings
):
    mock_evm_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_solana_response = {
        "result": {"items": [MOCK_SOLANA_ASSET_RESPONSE], "total": 1, "limit": 50}
    }

    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        mock_evm_response, mock_solana_response
    )
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(mock_evm_response)

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=&chains=ethereum,polygon,solana"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    assert len(sh_response.nfts) == 3


def test_get_simplehash_nfts_by_owner_no_wallet_addresses(
    mock_httpx_client, mock_settings
):
    mock_evm_response = {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": None,
    }

    mock_solana_response = {
        "result": {"items": [MOCK_SOLANA_ASSET_RESPONSE], "total": 1, "limit": 50}
    }

    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        mock_evm_response, mock_solana_response
    )
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(mock_evm_response)

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=&chains=ethereum,polygon,solana"
    )
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)

    assert len(sh_response.nfts) == 3


def test_get_nfts_by_ids_transforms_each_chain_with_its_own_chain(
    mock_httpx_client, mock_settings
):
    # Same upstream payload for every chain; only the chain grouping differs.
    mock_httpx_client.post.return_value.json.return_value = {
        "nfts": [MOCK_NFT_ALCHEMY_RESPONSE]
    }

    response = client.get(
        "/api/nft/v1/getNFTsByIds?ids=eth.0x1.0x123.456,eth.0x89.0x789.101112"
    )
    assert response.status_code == 200
    sh_response = SimpleHashNFTResponse.model_validate(response.json())

    # One upstream batch per chain, hitting that chain's Alchemy host
    hosts = [
        call.args[0].split("/")[2] for call in mock_httpx_client.post.call_args_list
    ]
    assert hosts == ["eth-mainnet.g.alchemy.com", "polygon-mainnet.g.alchemy.com"]

    # Each NFT must be tagged with the chain it was fetched from, not the last
    # chain seen while parsing the ids.
    assert [nft.chain for nft in sh_response.nfts] == ["ethereum", "polygon"]


def _http_status_error(url: str, status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", url)
    return httpx.HTTPStatusError(
        f"Client error '{status_code}' for url '{url}'",
        request=request,
        response=httpx.Response(status_code, request=request),
    )


def test_get_nfts_by_ids_upstream_http_error_is_502_without_key(
    mock_httpx_client, mock_settings, caplog
):
    url = "https://polygon-mainnet.g.alchemy.com/nft/v3/test_key/getNFTMetadataBatch"
    mock_httpx_client.post.return_value = _create_mock_response(400)
    mock_httpx_client.post.return_value.raise_for_status.side_effect = (
        _http_status_error(url, 400)
    )

    with caplog.at_level("WARNING"):
        response = client.get("/api/nft/v1/getNFTsByIds?ids=eth.0x89.0x789.101112")

    assert response.status_code == 502
    assert "test_key" not in response.text
    assert "test_key" not in caplog.text
    assert "getNFTMetadataBatch on polygon-mainnet failed with HTTP 400" in caplog.text


def test_get_nfts_by_owner_upstream_transport_error_is_502_without_key(
    mock_httpx_client, mock_settings, caplog
):
    url = "https://eth-mainnet.g.alchemy.com/nft/v3/test_key/getNFTsForOwner"
    mock_httpx_client.get.side_effect = httpx.ConnectError(
        "connection refused", request=httpx.Request("GET", url)
    )

    with caplog.at_level("WARNING"):
        response = client.get(
            "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1"
        )

    assert response.status_code == 502
    assert "test_key" not in response.text
    assert "test_key" not in caplog.text
    assert "getNFTsForOwner on eth-mainnet failed: ConnectError" in caplog.text


def test_get_nfts_by_ids_chunks_metadata_batches_to_alchemy_limit(
    mock_httpx_client, mock_settings
):
    captured_batches: list[list[dict]] = []
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        {"nfts": [MOCK_NFT_ALCHEMY_RESPONSE]}, None, captured_batches
    )

    ids = ",".join(f"eth.0x89.0x789.{token_id}" for token_id in range(150))
    response = client.get(f"/api/nft/v1/getNFTsByIds?ids={ids}")
    assert response.status_code == 200

    # 150 ids on one chain -> two upstream calls of 100 and 50 tokens. The
    # batches are issued concurrently, so order them by first token id.
    batches = sorted(captured_batches, key=lambda batch: int(batch[0]["tokenId"]))
    assert [len(batch) for batch in batches] == [100, 50]
    assert [batch[0]["tokenId"] for batch in batches] == ["0", "100"]

    # One NFT per upstream call -> both batches' results are concatenated
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert len(sh_response.nfts) == 2


def test_get_nfts_by_ids_fetches_chains_and_batches_concurrently(
    mock_httpx_client, mock_settings
):
    # Solana + two EVM chains, one needing two batches -> 4 upstream calls.
    # Each mocked call waits until all of them have been issued. A serial
    # implementation never issues the next call while one is pending, so it
    # times out and the request fails.
    barrier = asyncio.Barrier(4)

    async def post(url, json):
        await asyncio.wait_for(barrier.wait(), timeout=1)
        if "solana-mainnet" in url:
            return _create_mock_response(
                json_data={"result": [MOCK_SOLANA_ASSET_RESPONSE]}
            )
        return _create_mock_response(json_data={"nfts": [MOCK_NFT_ALCHEMY_RESPONSE]})

    mock_httpx_client.post.side_effect = post

    ids = ",".join(
        [f"sol.0x65.{MOCK_SPL_TOKEN_MINT_ADDRESS}"]
        + [f"eth.0x1.0x123.{token_id}" for token_id in range(101)]
        + ["eth.0x89.0x789.1"]
    )
    response = client.get(f"/api/nft/v1/getNFTsByIds?ids={ids}")
    assert response.status_code == 200
    assert mock_httpx_client.post.call_count == 4

    # One NFT per upstream call, returned as Solana first, then chains in
    # request order, regardless of which call resolved first
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert [nft.chain for nft in sh_response.nfts] == [
        "solana",
        "ethereum",
        "ethereum",
        "polygon",
    ]


def test_get_nfts_by_owner_fetches_chains_concurrently(
    mock_httpx_client, mock_settings
):
    # Two EVM chains (GET) and Solana (POST) -> 3 upstream calls, each of
    # which waits until all of them have been issued (see the getNFTsByIds
    # concurrency test above)
    barrier = asyncio.Barrier(3)

    async def get(url, params):
        await asyncio.wait_for(barrier.wait(), timeout=1)
        return _create_mock_response(
            json_data={
                "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
                "totalCount": 1,
                "pageKey": None,
            }
        )

    async def post(url, json):
        await asyncio.wait_for(barrier.wait(), timeout=1)
        return _create_mock_response(
            json_data={
                "result": {
                    "items": [MOCK_SOLANA_ASSET_RESPONSE],
                    "total": 1,
                    "limit": 50,
                }
            }
        )

    mock_httpx_client.get.side_effect = get
    mock_httpx_client.post.side_effect = post

    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123"
        "&chains=eth.0x1&chains=eth.0x89&chains=sol.0x65"
    )
    assert response.status_code == 200
    assert mock_httpx_client.get.call_count == 2
    assert mock_httpx_client.post.call_count == 1

    # Results follow the requested chain order regardless of which call
    # resolved first
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert [nft.chain for nft in sh_response.nfts] == ["ethereum", "polygon", "solana"]


def _owner_page(page_key=None):
    return {
        "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
        "totalCount": 1,
        "pageKey": page_key,
    }


def _network(url):
    return url.split("//")[1].split(".")[0]


def test_get_nfts_by_owner_paginates_each_chain_on_its_own(
    mock_httpx_client, mock_settings
):
    # Page 1: ethereum and polygon have more pages, optimism does not
    more = {"eth-mainnet": "eth_page2", "polygon-mainnet": "polygon_page2"}
    mock_httpx_client.get.side_effect = lambda url, params: _create_mock_response(
        json_data=_owner_page(more.get(_network(url)))
    )
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123"
        "&chains=eth.0x1&chains=eth.0x89&chains=eth.0xa"
    )
    assert response.status_code == 200
    cursor = response.json()["next_cursor"]
    assert _decode_owner_cursor(cursor) == more

    # Page 2: only the chains in the cursor are queried, each with its own key
    mock_httpx_client.get.reset_mock()
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(_owner_page())
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123"
        f"&chains=eth.0x1&chains=eth.0x89&chains=eth.0xa&page_key={cursor}"
    )
    assert response.status_code == 200
    sent = {
        _network(call.args[0]): call.kwargs["params"]["pageKey"]
        for call in mock_httpx_client.get.call_args_list
    }
    assert sent == more
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert [nft.chain for nft in sh_response.nfts] == ["ethereum", "polygon"]
    assert sh_response.next_cursor is None


def test_get_nfts_by_owner_walks_solana_pages(mock_httpx_client, mock_settings):
    def post(url, json):
        page = json["params"]["page"]
        # Page 1 is full (50 = the Solana page size); page 2 is short
        items = [MOCK_SOLANA_ASSET_RESPONSE] * (50 if page == 1 else 3)
        return _create_mock_response(
            json_data={"result": {"items": items, "total": len(items), "limit": 50}}
        )

    mock_httpx_client.post.side_effect = post

    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=mint123&chains=sol.0x65"
    )
    assert response.status_code == 200
    assert len(response.json()["nfts"]) == 50
    cursor = response.json()["next_cursor"]
    assert _decode_owner_cursor(cursor) == {"solana-mainnet": 2}

    response = client.get(
        f"/api/nft/v1/getNFTsForOwner?wallet_address=mint123&chains=sol.0x65&page_key={cursor}"
    )
    assert response.status_code == 200
    assert mock_httpx_client.post.call_args.kwargs["json"]["params"]["page"] == 2
    assert len(response.json()["nfts"]) == 3
    assert response.json()["next_cursor"] is None


@pytest.mark.parametrize(
    "cursor",
    [
        "not-a-cursor",  # valid base64 that is not JSON
        "abc",  # invalid base64 padding
        "e03eb4a0-0442-4b6c-9ab7-2c1f0d1c8f11",  # a raw Alchemy pageKey
    ],
)
def test_get_nfts_by_owner_treats_undecodable_cursor_as_legacy_page_key(
    mock_httpx_client, mock_settings, cursor
):
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(_owner_page())
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        None,
        {"result": {"items": [MOCK_SOLANA_ASSET_RESPONSE], "total": 1, "limit": 50}},
    )

    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123"
        f"&chains=eth.0x1&chains=eth.0x89&chains=sol.0x65&page_key={cursor}"
    )
    assert response.status_code == 200
    # Every EVM chain gets the raw key; Solana pages are integers so it is skipped
    assert [
        call.kwargs["params"]["pageKey"]
        for call in mock_httpx_client.get.call_args_list
    ] == [cursor, cursor]
    mock_httpx_client.post.assert_not_called()


def test_get_nfts_by_owner_rejects_non_numeric_solana_page(
    mock_httpx_client, mock_settings
):
    cursor = _encode_owner_cursor({Chain.SOLANA: "later"})
    response = client.get(
        f"/api/nft/v1/getNFTsForOwner?wallet_address=mint123&chains=sol.0x65&page_key={cursor}"
    )
    assert response.status_code == 400
    mock_httpx_client.post.assert_not_called()


def test_solana_asset_without_metadata_name_is_still_returned(
    mock_httpx_client, mock_settings
):
    nameless: dict[str, Any] = copy.deepcopy(MOCK_SOLANA_ASSET_RESPONSE)
    nameless["content"]["metadata"] = {}
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        None, {"result": {"items": [nameless], "total": 1, "limit": 50}}
    )

    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=mint123&chains=sol.0x65"
    )
    assert response.status_code == 200
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert len(sh_response.nfts) == 1
    assert sh_response.nfts[0].name is None


def test_get_simplehash_nfts_by_owner_requests_full_evm_pages(
    mock_httpx_client, mock_settings
):
    evm_params = []
    solana_bodies = []

    def get(url, params):
        evm_params.append(dict(params))
        return _create_mock_response(
            json_data={
                "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE],
                "totalCount": 1,
                "pageKey": None,
            }
        )

    def post(url, json):
        solana_bodies.append(json)
        return _create_mock_response(
            json_data={
                "result": {
                    "items": [MOCK_SOLANA_ASSET_RESPONSE],
                    "total": 1,
                    "limit": 50,
                }
            }
        )

    mock_httpx_client.get.side_effect = get
    mock_httpx_client.post.side_effect = post

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=0x123&chains=ethereum,polygon"
    )
    assert response.status_code == 200
    assert [p["pageSize"] for p in evm_params] == ["100", "100"]

    response = client.get(
        "/simplehash/api/v0/nfts/owners?wallet_addresses=mint123&chains=solana"
    )
    assert response.status_code == 200
    # Solana pages stay at 50: some wallets carry megabytes of metadata per asset
    assert solana_bodies[0]["params"]["limit"] == 50


def test_owner_cursor_decodes_without_base64_padding():
    cursor = _encode_owner_cursor({Chain.SOLANA: 2, Chain.ETHEREUM: "abc"})
    assert cursor is not None and cursor.endswith("=")
    assert _decode_owner_cursor(cursor.rstrip("=")) == _decode_owner_cursor(cursor)


def test_solana_nfts_carry_their_owner(mock_httpx_client, mock_settings):
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        None, {"result": [MOCK_SOLANA_ASSET_RESPONSE]}
    )
    response = client.get(
        f"/simplehash/api/v0/nfts/assets?nft_ids=solana.{MOCK_SPL_TOKEN_MINT_ADDRESS}"
    )
    assert response.status_code == 200
    nft = SimpleHashNFTResponse.model_validate(response.json()).nfts[0]
    assert nft.owners is not None
    assert [(o.owner_address, o.quantity) for o in nft.owners] == [
        ("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", 1)
    ]


@pytest.mark.parametrize(
    ("ownership", "expected"),
    [
        (None, None),
        ({"ownership_model": "token", "owner": "9WzD"}, None),
        ({"ownership_model": "single", "owner": None}, None),
    ],
)
def test_solana_owners_are_unknown_unless_single_owner(
    mock_httpx_client, mock_settings, ownership, expected
):
    asset = {**MOCK_SOLANA_ASSET_RESPONSE, "ownership": ownership}
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        None, {"result": [asset]}
    )
    response = client.get(
        f"/simplehash/api/v0/nfts/assets?nft_ids=solana.{MOCK_SPL_TOKEN_MINT_ADDRESS}"
    )
    assert response.status_code == 200
    assert response.json()["nfts"][0]["owners"] == expected


@pytest.mark.parametrize(
    ("spam_query", "upstream_filter", "expected_spam_scores"),
    [
        ("", None, [0, 1]),  # param omitted: everything, no upstream filter
        ("&spam=all", None, [0, 1]),
        ("&spam=exclude", "SPAM", [0]),
        ("&spam=only", None, [1]),
    ],
)
def test_get_simplehash_nfts_by_owner_spam_filter(
    mock_httpx_client, mock_settings, spam_query, upstream_filter, expected_spam_scores
):
    spam_nft: dict[str, Any] = copy.deepcopy(MOCK_NFT_ALCHEMY_RESPONSE)
    spam_nft["contract"]["isSpam"] = True
    mock_httpx_client.get.side_effect = _create_mock_get_side_effect(
        {
            "ownedNfts": [MOCK_NFT_ALCHEMY_RESPONSE, spam_nft],
            "totalCount": 2,
            "pageKey": None,
        }
    )
    response = client.get(
        f"/simplehash/api/v0/nfts/owners?wallet_addresses=0x123&chains=ethereum{spam_query}"
    )
    assert response.status_code == 200
    params = mock_httpx_client.get.call_args.kwargs["params"]
    assert params.get("excludeFilters[]") == upstream_filter
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert [
        nft.collection.spam_score for nft in sh_response.nfts
    ] == expected_spam_scores


def test_get_nfts_by_owner_spam_filter_applies_to_solana_heuristic(
    mock_httpx_client, mock_settings
):
    airdrop = {
        **MOCK_SOLANA_ASSET_RESPONSE,
        "grouping": [
            {
                "group_key": "collection",
                "group_value": "spamcoll",
                "collection_metadata": {"name": "Free Airdrop Box"},
            }
        ],
    }
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        None,
        {
            "result": {
                "items": [MOCK_SOLANA_ASSET_RESPONSE, airdrop],
                "total": 2,
                "limit": 50,
            }
        },
    )
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=mint123&chains=sol.0x65&spam=only"
    )
    assert response.status_code == 200
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert [nft.collection.name for nft in sh_response.nfts] == ["Free Airdrop Box"]


def test_get_nfts_by_owner_rejects_unknown_spam_filter(mock_settings):
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1&spam=maybe"
    )
    assert response.status_code == 422


def _owner_page_or_error(failing_networks, page_key=None):
    def get(url, params):
        network = _network(url)
        if network in failing_networks:
            raise _http_status_error(url, 502)
        return _create_mock_response(json_data=_owner_page(page_key))

    return get


def test_get_nfts_by_owner_skips_a_failed_chain(mock_httpx_client, mock_settings):
    mock_httpx_client.get.side_effect = _owner_page_or_error(
        {"polygon-mainnet"}, page_key="more"
    )
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123"
        "&chains=eth.0x1&chains=eth.0x89&chains=eth.0xa"
    )
    assert response.status_code == 200
    sh_response = SimpleHashNFTResponse.model_validate(response.json())
    assert [nft.chain for nft in sh_response.nfts] == ["ethereum", "optimism"]
    # The failed chain is not in the cursor either, so it is not retried
    assert sh_response.next_cursor is not None
    assert _decode_owner_cursor(sh_response.next_cursor) == {
        "eth-mainnet": "more",
        "opt-mainnet": "more",
    }


def test_get_nfts_by_owner_fails_when_every_chain_fails(
    mock_httpx_client, mock_settings
):
    mock_httpx_client.get.side_effect = _owner_page_or_error(
        {"eth-mainnet", "polygon-mainnet"}
    )
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1&chains=eth.0x89"
    )
    assert response.status_code == 502


def test_get_nfts_by_owner_does_not_swallow_unexpected_errors(
    mock_httpx_client, mock_settings
):
    mock_httpx_client.get.side_effect = RuntimeError("bug")
    with pytest.raises(RuntimeError):
        client.get("/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1")


def test_alchemy_call_times_out_as_502_without_key(
    mock_httpx_client, mock_settings, caplog, monkeypatch
):
    monkeypatch.setattr("app.api.nft.routes.ALCHEMY_NFT_CALL_TIMEOUT", 0.05)

    async def slow_get(url, params):
        await asyncio.sleep(0.5)
        return _create_mock_response(json_data=_owner_page())

    mock_httpx_client.get.side_effect = slow_get
    with caplog.at_level("WARNING"):
        response = client.get(
            "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1"
        )
    assert response.status_code == 502
    assert "Alchemy getNFTsForOwner on eth-mainnet timed out after 0s" in caplog.text
    assert "test_key" not in caplog.text


def test_alchemy_upstream_metrics_record_success_and_batch_size(
    mock_httpx_client, mock_settings, metric_value
):
    labels = {"method": "getNFTMetadataBatch", "network": "polygon-mainnet"}

    def snapshot():
        return (
            metric_value("alchemy_nft_upstream_requests_total", **labels, status="200"),
            metric_value("alchemy_nft_upstream_duration_seconds_count", **labels),
            metric_value("alchemy_nft_batch_size_count", **labels),
            metric_value("alchemy_nft_batch_size_sum", **labels),
        )

    ok, durations, batches, batch_sum = snapshot()
    mock_httpx_client.post.side_effect = _create_mock_post_side_effect(
        {"nfts": [MOCK_NFT_ALCHEMY_RESPONSE]}, None
    )
    ids = ",".join(f"eth.0x89.0x789.{token_id}" for token_id in range(150))
    response = client.get(f"/api/nft/v1/getNFTsByIds?ids={ids}")
    assert response.status_code == 200

    # Two batches (100 + 50) -> two successful timed calls, 150 tokens in total
    assert snapshot() == (ok + 2, durations + 2, batches + 2, batch_sum + 150)


def test_alchemy_upstream_metrics_record_http_and_transport_failures(
    mock_httpx_client, mock_settings, metric_value
):
    def requests(status):
        return metric_value(
            "alchemy_nft_upstream_requests_total",
            method="getNFTsForOwner",
            network="eth-mainnet",
            status=status,
        )

    before_400, before_connect = requests("400"), requests("ConnectError")

    url = "https://eth-mainnet.g.alchemy.com/nft/v3/test_key/getNFTsForOwner"
    mock_httpx_client.get.return_value = _create_mock_response(status_code=400)
    mock_httpx_client.get.return_value.raise_for_status.side_effect = (
        _http_status_error(url, 400)
    )
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1"
    )
    assert response.status_code == 502
    assert requests("400") == before_400 + 1

    mock_httpx_client.get.side_effect = httpx.ConnectError("boom")
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1"
    )
    assert response.status_code == 502
    assert requests("ConnectError") == before_connect + 1


def test_owner_page_metrics_split_spam_from_real_nfts(
    mock_httpx_client, mock_settings, metric_value
):
    def page(spam):
        return (
            metric_value("nft_owner_page_nfts_count", network="eth-mainnet", spam=spam),
            metric_value("nft_owner_page_nfts_sum", network="eth-mainnet", spam=spam),
        )

    real_pages, real_sum = page("false")
    spam_pages, spam_sum = page("true")

    spam_nft: dict[str, Any] = copy.deepcopy(MOCK_NFT_ALCHEMY_RESPONSE)
    spam_nft["contract"]["isSpam"] = True
    mock_httpx_client.get.return_value = _create_mock_response(
        json_data={
            "ownedNfts": [
                MOCK_NFT_ALCHEMY_RESPONSE,
                MOCK_NFT_ALCHEMY_RESPONSE,
                spam_nft,
            ],
            "totalCount": 3,
            "pageKey": None,
        }
    )
    response = client.get(
        "/api/nft/v1/getNFTsForOwner?wallet_address=0x123&chains=eth.0x1"
    )
    assert response.status_code == 200

    # One page observed on each series: 2 real NFTs, 1 spam
    assert page("false") == (real_pages + 1, real_sum + 2)
    assert page("true") == (spam_pages + 1, spam_sum + 1)
