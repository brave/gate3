from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class PhishingLookupResponse(BaseModel):
    """Full-hash candidates for each submitted 4-byte prefix."""

    version: str = Field(description="Ingested eth-phishing-detect list version")
    matches: dict[str, list[str]] = Field(
        description=(
            "Map of requested 8-hex prefixes to full 64-hex SHA-256 hashes "
            "sharing that prefix"
        )
    )

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PhishingRefreshResponse(BaseModel):
    status: str
    message: str
    version: str | None = None
    entry_count: int | None = None
    hash_count: int | None = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )
