import uuid
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchField, SearchFieldDataType, SearchIndex,
    VectorSearch, HnswAlgorithmConfiguration, VectorSearchProfile,
    AzureOpenAIVectorizer, AzureOpenAIVectorizerParameters
)
from config.load_config import get_search_credentials, get_model_config

search_config = get_search_credentials()
model_cfg = get_model_config()

index_name = model_cfg["azure_ai_search"]["index_name"]

search_client = SearchClient(
    endpoint=search_config["endpoint"],
    index_name=index_name,
    credential=AzureKeyCredential(search_config["key"])
)

index_client = SearchIndexClient(
    endpoint=search_config["endpoint"],
    credential=AzureKeyCredential(search_config["key"])
)

def create_clause_index():
    """
    Create or update the Azure Cognitive Search index for clause prototypes.

    This index will store:
      - id: unique document key
      - cluster_id: integer grouping of clauses
      - clause: the clause text
      - embedding: vector field for semantic search

    It uses HNSW for vector search and Azure OpenAI as the vectorizer.
    """
    # Define the index schema fields
    fields = [
        SearchField(name="id", type=SearchFieldDataType.String, key=True),
        SearchField(name="cluster_id", type=SearchFieldDataType.Int32, filterable=True),
        SearchField(name="clause", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            vector_search_dimensions=1536,
            vector_search_profile_name="myHnswProfile"
        )
    ]
    # Configure vector search: HNSW algorithm and profile
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
                    resource_url="https://logicalis-latam-ai-eastus.openai.azure.com",  # OpenAI endpoint
                    deployment_name=model_cfg["openai_models"]["embeddings"]["deployment"],
                    model_name=model_cfg["openai_models"]["embeddings"]["model_name"]
                ),
            )
        ]
    )
    # Assemble the index definition
    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    # Create or update the index in Azure Cognitive Search
    result = index_client.create_or_update_index(index)
    # Log the created index name
    print(f"Index '{result.name}' created successfully.")


def upload_prototype_clauses(df):
    """
    Upload prototype clauses from a DataFrame into the search index.

    Each row in `df` should have:
      - 'cluster': cluster ID (numeric)
      - 'content': clause text

    Documents are assigned a random UUID for the 'id' field.
    """
    documents = []
    # Build document payloads for each DataFrame row
    for _, row in df.iterrows():
        documents.append({
            "id": str(uuid.uuid4()),             # unique document identifier
            "cluster_id": int(row['cluster']),    # group ID
            "clause": row['content']              # the clause text
        })
    # Upload documents to the search index
    result = search_client.upload_documents(documents=documents)
    # Report how many documents were indexed
    print(f"Uploaded {len(result)} documents successfully.")


def search_similar_clause(embedding, new_clause, k=1):
    """
    Query the search index for the most semantically similar clause.

    Parameters:
        embedding (List[float]): Precomputed embedding vector for the new clause.
        new_clause (str): The text to use as fallback search_text.
        k (int): Number of nearest neighbors to retrieve (default 1).

    Returns:
        The top search result (first document) from the index.
    """
    # Execute a vector search with optional text fallback
    results = search_client.search(
        search_text=new_clause,
        vector_queries=[{"value": embedding}],
        top_k=k
    )
    # Return the first matching document
    return list(results)[0]