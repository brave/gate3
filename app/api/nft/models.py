from enum import Enum

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel


class AlchemyTokenType(str, Enum):
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"


class AlchemyContract(BaseModel):
    address: str
    name: str | None = None
    symbol: str | None = None
    is_spam: bool | None = None
    spam_classifications: list[str] = Field(default_factory=list)

    class Config:
        alias_generator = to_camel


class AlchemyImage(BaseModel):
    cached_url: str | None = None
    thumbnail_url: str | None = None
    png_url: str | None = None
    content_type: str | None = None
    size: int | None = None
    original_url: str | None = None

    class Config:
        alias_generator = to_camel


class AlchemyAttribute(BaseModel):
    trait_type: str
    value: str | bool | int | float | None = None


class AlchemyRawMetadata(BaseModel):
    name: str | None = None
    description: str | None = None
    image: str | None = None
    external_url: str | None = None
    attributes: list[AlchemyAttribute] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict)

    class Config:
        alias_generator = to_camel


class AlchemyRaw(BaseModel):
    token_uri: str | None = None
    metadata: AlchemyRawMetadata | None = None
    error: str | None = None

    class Config:
        alias_generator = to_camel


class AlchemyNFT(BaseModel):
    contract: AlchemyContract
    token_id: str
    token_type: AlchemyTokenType
    name: str | None = None
    description: str | None = None
    image: AlchemyImage | None = None
    raw: AlchemyRaw | None = None
    token_uri: str | None = None

    class Config:
        alias_generator = to_camel


class AlchemyNFTResponse(BaseModel):
    owned_nfts: list[AlchemyNFT]
    page_key: str | None = None

    class Config:
        alias_generator = to_camel


class AlchemyChain(str, Enum):
    ETHEREUM = "eth-mainnet"
    POLYGON = "polygon-mainnet"
    BASE = "base-mainnet"
    OPTIMISM = "opt-mainnet"
    ARBITRUM = "arb-mainnet"
    SOLANA = "sol-mainnet"


# SimpleHash Models
class SimpleHashChain(str, Enum):
    ETHEREUM = "ethereum"
    BSC = "bsc"
    AVALANCHE = "avalanche"
    POLYGON = "polygon"
    BASE = "base"
    OPTIMISM = "optimism"
    ARBITRUM = "arbitrum"
    SOLANA = "solana"


class SimpleHashTokenType(str, Enum):
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"


class SimpleHashContract(BaseModel):
    type: SimpleHashTokenType
    name: str | None = None
    symbol: str | None = None


class SimpleHashCollection(BaseModel):
    name: str
    spam_score: int | None = None


class SimpleHashAttribute(BaseModel):
    trait_type: str
    value: str | bool | int | float | None = None


class SimpleHashExtraMetadata(BaseModel):
    attributes: list[SimpleHashAttribute] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict)
    image_original_url: str | None = None
    animation_original_url: str | None = None
    metadata_original_url: str | None = None


class SimpleHashNFT(BaseModel):
    chain: SimpleHashChain
    contract_address: str
    token_id: str
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    background_color: str | None = None
    external_url: str | None = None
    contract: SimpleHashContract
    collection: SimpleHashCollection
    extra_metadata: SimpleHashExtraMetadata


class SimpleHashNFTResponse(BaseModel):
    next_cursor: str | None = None
    nfts: list[SimpleHashNFT]


class SolanaAssetMerkleProof(BaseModel):
    node_index: int
    tree_id: str
    proof: list[str]
    root: str | None = None
    leaf: str | None = None
