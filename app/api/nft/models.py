from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


def strip_trailing_slash_validator(v: str | None) -> str | None:
    if v is not None:
        return v.strip().rstrip("/")
    return v


class AlchemyTokenType(str, Enum):
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"


class AlchemyContract(BaseModel):
    address: str
    name: str | None = None
    symbol: str | None = None
    is_spam: bool | None = None
    spam_classifications: list[str] = Field(default_factory=list)

    model_config = ConfigDict(alias_generator=to_camel)


class AlchemyImage(BaseModel):
    cached_url: str | None = None
    thumbnail_url: str | None = None
    png_url: str | None = None
    content_type: str | None = None
    size: int | None = None
    original_url: str | None = None

    @field_validator("cached_url", "thumbnail_url", "png_url", "original_url")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        return strip_trailing_slash_validator(v)

    model_config = ConfigDict(alias_generator=to_camel)


class TraitAttribute(BaseModel):
    trait_type: str
    value: str | bool | int | float | None = None


class AlchemyRawMetadata(BaseModel):
    image: str | None = None
    external_url: str | None = None
    attributes: list[TraitAttribute] = Field(default_factory=list)

    @field_validator("image")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        return strip_trailing_slash_validator(v)

    @field_validator("attributes", mode="before")
    @classmethod
    def validate_attributes(cls, v):
        if isinstance(v, list):
            # Already in the correct format
            return v
        else:
            # Return empty list for any other type (dict, string, etc.)
            return []

    model_config = ConfigDict(alias_generator=to_camel)


class AlchemyRaw(BaseModel):
    token_uri: str | None = None
    metadata: AlchemyRawMetadata | str | None = None
    error: str | None = None

    model_config = ConfigDict(alias_generator=to_camel)


class AlchemyNFT(BaseModel):
    contract: AlchemyContract
    token_id: str
    token_type: AlchemyTokenType
    name: str | None = None
    description: str | None = None
    image: AlchemyImage | None = None
    raw: AlchemyRaw | None = None
    token_uri: str | None = None

    model_config = ConfigDict(alias_generator=to_camel)


class AlchemyNFTResponse(BaseModel):
    owned_nfts: list[AlchemyNFT]
    page_key: str | None = None

    model_config = ConfigDict(alias_generator=to_camel)


class SimpleHashTokenType(str, Enum):
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"
    NON_FUNGIBLE = "NonFungible"


class SimpleHashContract(BaseModel):
    type: SimpleHashTokenType
    name: str | None = None
    symbol: str | None = None


class SimpleHashCollection(BaseModel):
    name: str | None = None
    spam_score: int | None = None


class SimpleHashExtraMetadata(BaseModel):
    attributes: list[TraitAttribute] = Field(default_factory=list)
    image_original_url: str | None = None
    animation_original_url: str | None = None
    metadata_original_url: str | None = None


class SimpleHashNFT(BaseModel):
    chain: str
    contract_address: str
    token_id: str | None = None
    name: str | None = None
    description: str | None = None
    image_url: str | None = None
    background_color: str | None = None
    external_url: str | None = None
    contract: SimpleHashContract
    collection: SimpleHashCollection
    extra_metadata: SimpleHashExtraMetadata

    @field_validator("image_url")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        return strip_trailing_slash_validator(v)


class SimpleHashNFTResponse(BaseModel):
    next_cursor: str | None = None
    nfts: list[SimpleHashNFT]


class SolanaAssetMerkleProof(BaseModel):
    node_index: int
    tree_id: str
    proof: list[str]
    root: str | None = None
    leaf: str | None = None

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        json_encoders={dict: lambda v: v if v else {}},
    )


class SolanaAssetRawContent(BaseModel):
    name: str
    symbol: str | None = None
    description: str | None = None
    image: str | None = None


class SolanaAssetContentFile(BaseModel):
    uri: str
    mime: str

    @field_validator("uri")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        return strip_trailing_slash_validator(v)


class SolanaAssetContentLink(BaseModel):
    image: Any = None
    external_url: str | None = None

    @field_validator("image")
    @classmethod
    def validate_image(cls, v: Any) -> str | None:
        if isinstance(v, str):
            return strip_trailing_slash_validator(v) or None

        return None

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        json_encoders={dict: lambda v: v if v else {}},
    )


class SolanaAssetContentMetadata(BaseModel):
    name: str
    symbol: str | None = None
    description: str | None = None
    attributes: list[TraitAttribute] = Field(default_factory=list)


class SolanaAssetContent(BaseModel):
    json_uri: str | None = None
    files: list[SolanaAssetContentFile] = Field(default_factory=list)
    metadata: SolanaAssetContentMetadata | None = None
    links: SolanaAssetContentLink | None = None


class SolanaAssetGroupingCollectionMetadata(BaseModel):
    name: str | None = None
    external_url: str | None = None
    image: str | None = None
    symbol: str | None = None

    @field_validator("image")
    @classmethod
    def validate_urls(cls, v: str | None) -> str | None:
        return strip_trailing_slash_validator(v)

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        json_encoders={dict: lambda v: v if v else {}},
    )


class SolanaAssetGrouping(BaseModel):
    group_key: str
    group_value: str
    collection_metadata: SolanaAssetGroupingCollectionMetadata | None = None


class SolanaAsset(BaseModel):
    interface: str
    id: str
    content: SolanaAssetContent
    grouping: list[SolanaAssetGrouping] = Field(default_factory=list)
    mutable: bool
    burnt: bool


class SolanaAssetResponse(BaseModel):
    total: int
    limit: int
    cursor: str | None = None
    items: list[SolanaAsset]
