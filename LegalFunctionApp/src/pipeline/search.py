"""
Azure Cognitive Search index operations for clause review.

Handles temporary index creation for clause-level redundancy detection
and bulk vectorization/upload of reviewed clauses.
"""

import uuid

from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchIndexerDataNoneIdentity,
    VectorSearch,
    VectorSearchProfile,
)

from src.pipeline.embedding import generate_embedding


def create_temp_index(search_index, deployment_name, model_name, resource_url):
    """
    Create a temporary Azure Cognitive Search index for clause embeddings.

    Used during redundancy detection: reviewed clauses are indexed so that
    semantically similar clauses can be found and compared.

    Parameters:
        search_index: SearchIndexClient for managing indexes.
        deployment_name (str): Azure OpenAI deployment for the vectorizer.
        model_name (str): Embedding model name (e.g., "text-embedding-ada-002").
        resource_url (str): Azure OpenAI resource URL.

    Returns:
        str: The name of the newly created temporary index.
    """
    tmp_index_name = f"tmp_clause_{uuid.uuid4().hex[:8]}"

    fields = [
        SearchField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(
            name="numero_da_clausula",
            type=SearchFieldDataType.String,
            filterable=True,
            searchable=True,
        ),
        SearchField(
            name="clasula_original", type=SearchFieldDataType.String, searchable=True
        ),
        SearchField(
            name="problema_juridico", type=SearchFieldDataType.String, searchable=True
        ),
        SearchField(
            name="clausula_revisada", type=SearchFieldDataType.String, searchable=True
        ),
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
                vectorizer_name="clauseVector",
            )
        ],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name="clauseVector",
                kind="azureOpenAI",
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=resource_url,
                    deployment_name=deployment_name,
                    auth_identity=SearchIndexerDataNoneIdentity(),
                    model_name=model_name,
                ),
            )
        ],
    )

    index = SearchIndex(name=tmp_index_name, fields=fields, vector_search=vector_search)
    search_index.create_or_update_index(index)
    return tmp_index_name


def vectorize_and_upload(data, index_client, embeddings_client):
    """
    Generate embeddings for each clause and upload to Azure Cognitive Search.

    Parameters:
        data (dict): Mapping of page keys to dicts with 'clauses' lists.
        index_client: SearchClient with upload_documents method.
        embeddings_client: AzureOpenAI client configured for embeddings.

    Returns:
        int: Number of documents uploaded.
    """
    documents = []
    for page_key, page in data.items():
        for clause in page["clauses"]:
            documents.append(
                {
                    "id": clause["id"],
                    "numero_da_clausula": clause["numero_da_clausula"],
                    "clasula_original": clause["clasula_original"],
                    "problema_juridico": clause["problema_juridico"],
                    "clausula_revisada": clause["clausula_revisada"],
                    "embedding": generate_embedding(
                        embeddings_client, clause["clasula_original"]
                    ),
                }
            )
    result = index_client.upload_documents(documents=documents)
    return len(result)
