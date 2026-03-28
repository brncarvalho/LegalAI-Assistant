from typing import list

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    query: str

    limit: int = Field(default=5, ge=1, le=20)

    model_config = ConfigDict(populate_by_name=True)


class SearchResult(BaseModel):
    content: str = Field(alias="chunk")

    score: float = Field(alias="@search.score", default=0.0)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class SearchResponse(BaseModel):
    results: list[SearchResult]
