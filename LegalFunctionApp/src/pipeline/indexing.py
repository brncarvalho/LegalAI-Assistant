"""
Azure Cognitive Search index management.

Creates indexes, uploads prototype clauses, and performs similarity searches.
"""

import uuid
from azure.search.documents.indexes.models import (
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
)

from src.config.load_config import get_model_config


def create_clause_index(index_client, settings):
    """
    Create or update the Azure Cognitive Search index for clause prototypes.

    Parameters:
        index_client: An initialized SearchIndexClient.
        settings: Application Settings with azure_openai_resource_url.
    """
    model_cfg = get_model_config()
    index_name = model_cfg["azure_ai_search"]["index_name"]
    embeddings_cfg = model_cfg["openai_models"]["embeddings"]

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
                    deployment_name=embeddings_cfg["deployment"],
                    model_name=embeddings_cfg["model_name"],
                ),
            )
        ],
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    result = index_client.create_or_update_index(index)
    return result.name


def upload_prototype_clauses(search_client, df):
    """
    Upload prototype clauses from a DataFrame into the search index.

    Parameters:
        search_client: An initialized SearchClient.
        df: DataFrame with 'cluster' and 'content' columns.
    """
    documents = []
    for _, row in df.iterrows():
        documents.append({
            "id": str(uuid.uuid4()),
            "cluster_id": int(row['cluster']),
            "clause": row['content'],
        })

    result = search_client.upload_documents(documents=documents)
    return len(result)


def search_similar_clause(search_client, embedding, new_clause, k=1):
    """
    Query the search index for semantically similar clauses.

    Parameters:
        search_client: An initialized SearchClient.
        embedding (list[float]): Precomputed embedding vector.
        new_clause (str): Fallback text for hybrid search.
        k (int): Number of nearest neighbors.

    Returns:
        The top search result document.
    """
    results = search_client.search(
        search_text=new_clause,
        vector_queries=[{"value": embedding}],
        top_k=k,
    )
    return list(results)[0]
