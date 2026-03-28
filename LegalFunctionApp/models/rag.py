from pydantic import BaseModel


class RAGRequest(BaseModel):
    query: str
    limit: int = 5


class RAGResponse(BaseModel):
    query: str
    answer: str
