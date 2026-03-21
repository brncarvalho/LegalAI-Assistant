from openai import AzureOpenAI
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI, DefaultHttpxClient
import httpx

from src.config.load_config import (
    get_model_config,
    get_doc_intelligence_credentials,
    get_openai_credentials,
    get_embeddings_credentials,
    get_search_credentials,
)



def get_openai_client(model_key: str = "gpt_4o_mini") -> AzureOpenAI:
    """
    Create and return an AzureOpenAI client for language model requests.

    Parameters:
        model_key (str): Key to select which model configuration to use from
            the 'openai_models' section of the loaded model_config.yaml.
            Defaults to "gpt_4o_mini".

    Returns:
        AzureOpenAI: An instance of the AzureOpenAI client configured with
            the specified model's API version and endpoint/key credentials.
    """
    # load endpoint and key for Azure OpenAI from environment
    credentials = get_openai_credentials()
    # fetch the model-specific configuration (e.g., api_version) from YAML
    model_config = get_model_config()["openai_models"][model_key]

    timeout = httpx.Timeout(
    connect=5.0,  # tempo para abrir conexão
    read=90.0,    # tempo máximo esperando resposta
    write=5.0,    # tempo máximo para enviar o corpo da requisição
    pool=5.0      # tempo máximo esperando por uma conexão do pool
)
    httpx_client = httpx.Client(timeout=timeout)


    # instantiate and return the AzureOpenAI client
    return AzureOpenAI(
        api_version=model_config["api_version"],  # API version for this model
        azure_endpoint=credentials["endpoint"],   # the Azure OpenAI endpoint URL
        api_key=credentials["key"],
        http_client=httpx_client       # the Azure OpenAI API key
    )



def get_embeddings_openai_client(model_key: str = "embeddings") -> AzureOpenAI:
    """
    Create and return an AzureOpenAI client specifically for embedding requests.

    Parameters:
        model_key (str): Key to select which embeddings model configuration to use
            from the 'openai_models' section of the loaded model_config.yaml.
            Defaults to "embeddings".

    Returns:
        AzureOpenAI: An instance of the AzureOpenAI client configured for embeddings.
    """
    # load endpoint and key for embeddings service from environment
    credentials = get_embeddings_credentials()
    # fetch the embeddings model configuration from YAML
    model_config = get_model_config()["openai_models"][model_key]

    # instantiate and return the AzureOpenAI client for embeddings
    return AzureOpenAI(
        api_version=model_config["api_version"],  # API version for embeddings model
        azure_endpoint=credentials["endpoint"],   # embeddings service endpoint
        api_key=credentials["key"],               # embeddings service API key
    )



def get_document_intelligence_client() -> DocumentIntelligenceClient:
    """
    Create and return a DocumentIntelligenceClient for Azure Document Intelligence.

    Returns:
        DocumentIntelligenceClient: Configured client for analyzing documents
            using the prebuilt/form-trained models.
    """
    # load endpoint and key for Document Intelligence from environment
    credentials = get_doc_intelligence_credentials()
    # instantiate and return the DocumentIntelligenceClient
    return DocumentIntelligenceClient(
        endpoint=credentials["endpoint"],                # the DocIntelligence endpoint URL
        credential=AzureKeyCredential(credentials["key"])  # API key wrapped in AzureKeyCredential
    )


def get_ai_search_client(
    index_name: str = get_model_config()["azure_ai_search"]["index_name"]
) -> SearchClient:
    """
    Create and return a SearchClient for Azure Cognitive Search operations.

    Parameters:
        index_name (str): Name of the search index to operate on, taken by default from
            the 'azure_ai_search.index_name' value in model_config.yaml.

    Returns:
        SearchClient: Configured client to query and manage documents within the specified index.
    """
    # load endpoint and key for Azure Search from environment
    credentials = get_search_credentials()
    # instantiate and return the SearchClient for the given index
    return SearchClient(
        endpoint=credentials["endpoint"],        # Azure Search service endpoint
        index_name=index_name,                   # target index name
        credential=AzureKeyCredential(credentials["key"]),  # API key credential
    )


def get_ai_indexing_client() -> SearchIndexClient:
    """
    Create and return a SearchIndexClient for Azure Cognitive Search index management.

    Returns:
        SearchIndexClient: Configured client for creating, updating, or deleting search indexes.
    """
    # load endpoint and key for Azure Search from environment
    credentials = get_search_credentials()
    # instantiate and return the SearchIndexClient
    return SearchIndexClient(
        endpoint=credentials["endpoint"],                # Azure Search service endpoint
        credential=AzureKeyCredential(credentials["key"])  # API key credential
    )

