from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

from app.api.nft.models import (
    SimpleHashNFTResponse,
    SolanaAssetMerkleProof,
)
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

    # Mock the AsyncClient constructor to return our mock context manager
    monkeypatch.setattr("httpx.AsyncClient", lambda: mock_context)

    return mock_client


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


def test_get_solana_asset_proof_error(mock_httpx_client):
    mock_response = {
        "error": "Token not found",
    }
    mock_httpx_client.post.return_value = AsyncMock(
        status_code=200,
        json=Mock(return_value=mock_response),
        raise_for_status=Mock(return_value=None),
    )

    with pytest.raises(ValueError) as e:
        client.get("/api/nft/v1/getSolanaAssetProof?token_address=invalid_token")

    assert str(e.value) == "Alchemy API error: Token not found"


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
    assert sh_response.next_cursor == "next_page_key"


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
    mock_solana_asset = {
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
        "mutable": False,
        "burnt": False,
    }

    mock_response = {
        "result": [mock_solana_asset],
    }

    mock_httpx_client.post.return_value.json.return_value = mock_response

    response = client.get("/simplehash/api/v0/nfts/assets?nft_ids=solana.mint123")
    assert response.status_code == 200
    data = response.json()
    sh_response = SimpleHashNFTResponse.model_validate(data)
    assert len(sh_response.nfts) == 1


def test_get_simplehash_nfts_by_ids(mock_httpx_client, mock_settings):
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
        "result": [
            {
                "id": "0xdef123",
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
                "mutable": False,
                "burnt": False,
            }
        ],
    }

    # Track the actual requests made to capture the tokens array
    captured_requests = []

    def capture_post_request(*args, **kwargs):
        # Capture the request data
        if "json" in kwargs and "tokens" in kwargs["json"]:
            captured_requests.append(kwargs["json"]["tokens"])

        # Return a mock response
        mock_response_obj = Mock()
        mock_response_obj.status_code = 200

        # Return different responses based on the URL
        if "solana-mainnet" in str(args[0]) if args else False:
            mock_response_obj.json.return_value = mock_solana_response
        else:
            mock_response_obj.json.return_value = mock_response

        mock_response_obj.raise_for_status.return_value = None
        return mock_response_obj

    mock_httpx_client.post.side_effect = capture_post_request

    # Test with various malformed inputs that should be gracefully handled:
    # - Valid EVM ID: eth.0x1.0x123.456
    # - Valid EVM ID with trailing comma: eth.0x1.0x789.101112, (should be processed as valid)
    # - Missing token_id: eth.0x1.0xabc. (should be skipped)
    # - Empty string: (empty) (should be skipped)
    # - Invalid chain ID: eth.0x999.0xinvalid (should be skipped)
    # - Valid Solana ID: sol.0x65.0xdef123 (should be processed as valid)
    # - Malformed Solana ID: sol.0x65. (missing address, should be skipped)
    # - Malformed Solana ID: sol.0x65.0xdef123.extra (too many parts, should be skipped)
    # - Invalid Solana chain ID: sol.0x999.0xdef123 (invalid chain ID, should be skipped)
    response = client.get(
        "/api/nft/v1/getNFTsByIds?ids="
        "eth.0x1.0x123.456,"
        "eth.0x1.0x789.101112,"
        "eth.0x1.0xabc.,"
        "eth.0x999.0xinvalid,"
        "sol.0x65.0xdef123,"
        "sol.0x65.,"
        "sol.0x65.0xdef123.extra,"
        "sol.0x999.0xdef123"
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
