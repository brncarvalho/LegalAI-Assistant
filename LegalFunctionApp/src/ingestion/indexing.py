"""
Azure Cognitive Search index management.

Creates indexes, uploads prototype clauses, and performs similarity searches.
"""

import uuid

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    VectorSearch,
    VectorSearchProfile,
)
from pandas import DataFrame

from config.settings import settings


class IndexingService:
    def __init__(self):
        self.client = SearchIndexClient(
            endpoint=settings.azure_ai_search_endpoint,
            credential=AzureKeyCredential(settings.azure_ai_search_api_key),
        )

    def create_clause_index(self, index_name):
        """
        Create or update the Azure Cognitive Search index for clause prototypes.

        Parameters:
            index_client: An initialized SearchIndexClient.
            settings: Application Settings with azure_openai_resource_url.
        """

        fields = [
            SearchField(name="id", type=SearchFieldDataType.String, key=True),
            SearchField(name="cluster_id", type=SearchFieldDataType.Int32, filterable=True),
            SearchField(name="clause", type=SearchFieldDataType.String, searchable=True),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                vector_search_dimensions=1536,
                vector_search_profile_name="myHnswProfile",
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="myHnsw")],
            profiles=[
                VectorSearchProfile(
                    name="myHnswProfile",
                    algorithm_configuration_name="myHnsw",
                    vectorizer_name="myOpenAI",
                )
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    vectorizer_name="myOpenAI",
                    kind="azureOpenAI",
                    parameters=AzureOpenAIVectorizerParameters(
                        resource_url=settings.azure_openai_resource_url,
                        deployment_name=settings.embedding_model,
                        model_name=settings.embedding_model,
                    ),
                )
            ],
        )

        index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
        result = self.client.create_or_update_index(index)
        return result.name

    def upload_prototype_clauses(self, df: DataFrame):
        """
        Upload prototype clauses from a DataFrame into the search index.

        Parameters:
            search_client: An initialized SearchClient.
            df: DataFrame with 'cluster' and 'content' columns.
        """
        documents = []
        for _, row in df.iterrows():
            documents.append(
                {
                    "id": str(uuid.uuid4()),
                    "cluster_id": int(row["cluster"]),
                    "clause": row["content"],
                }
            )

        result = self.client.upload_documents(documents=documents)
        return len(result)
