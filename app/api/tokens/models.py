from pydantic import BaseModel, Field

from app.api.common.models import TokenInfo


class TokenSearchResponse(BaseModel):
    results: list[TokenInfo] = Field(..., description="Search results")
    offset: int = Field(..., description="Offset for pagination")
    limit: int = Field(..., description="Limit for pagination")
    total: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Search query")
