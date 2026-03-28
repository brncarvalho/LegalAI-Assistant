from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery

from models.search import SearchResponse, SearchResult


class SearchService:
    def __init__(self, ai_search_url: str, ai_search_api_key: str, index_name: str):
        self.azure_ai_search = SearchClient(
            endpoint=ai_search_url,
            index_name=index_name,
            credential=AzureKeyCredential(ai_search_api_key),
        )
        self.index_name = index_name

    def search(self, query: str, limit: int = 5):

        vector_query = VectorizableTextQuery(
            text=query,
            k_nearest_neighbors=5,
            fields="text_vector",
        )

        results = list(
            self.azure_ai_search.search(
                search_text=None,
                vector_queries=[vector_query],
                select=["chunk"],
                top=limit,
            )
        )

        retrieved_clauses = [
            SearchResult(content=result["chunk"], score=result["@search.score"])
            for result in results
        ]

        return SearchResponse(results=retrieved_clauses)
