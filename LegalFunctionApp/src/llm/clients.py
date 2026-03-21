"""
Client factory functions for Azure services.

Each function receives a Settings object (dependency injection) instead of
calling os.getenv() internally. This means:
- No module-level side effects (safe to import without env vars set)
- Testable: pass a mock Settings in tests
- Explicit: the caller controls which config is used
"""

import httpx
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

from src.config.load_config import get_model_config
from src.config.settings import Settings


def get_openai_client(settings: Settings, model_key: str = "gpt_4o") -> AzureOpenAI:
    """
    Create an AzureOpenAI client for LLM requests.

    Parameters:
        settings: Application settings with Azure OpenAI credentials.
        model_key: Which model config to use from model_config.yaml.
    """
    model_config = get_model_config()["openai_models"][model_key]

    timeout = httpx.Timeout(connect=5.0, read=90.0, write=5.0, pool=5.0)
    http_client = httpx.Client(timeout=timeout)

    return AzureOpenAI(
        api_version=model_config["api_version"],
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        http_client=http_client,
    )


def get_embeddings_openai_client(
    settings: Settings, model_key: str = "embeddings"
) -> AzureOpenAI:
    """Create an AzureOpenAI client for embedding requests."""
    model_config = get_model_config()["openai_models"][model_key]

    return AzureOpenAI(
        api_version=model_config["api_version"],
        azure_endpoint=settings.embeddings_openai_endpoint,
        api_key=settings.embeddings_openai_api_key,
    )


def get_document_intelligence_client(settings: Settings) -> DocumentIntelligenceClient:
    """Create a DocumentIntelligenceClient for PDF analysis."""
    return DocumentIntelligenceClient(
        endpoint=settings.azure_ai_doc_intelligence_endpoint,
        credential=AzureKeyCredential(settings.azure_ai_doc_intelligence_api_key),
    )


def get_ai_search_client(settings: Settings, index_name: str | None = None) -> SearchClient:
    """
    Create a SearchClient for querying an Azure Cognitive Search index.

    Parameters:
        settings: Application settings with Azure Search credentials.
        index_name: Override the index name. Defaults to the value in model_config.yaml.
    """
    if index_name is None:
        index_name = get_model_config()["azure_ai_search"]["index_name"]

    return SearchClient(
        endpoint=settings.azure_ai_search_endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(settings.azure_ai_search_api_key),
    )


def get_ai_indexing_client(settings: Settings) -> SearchIndexClient:
    """Create a SearchIndexClient for managing search indexes."""
    return SearchIndexClient(
        endpoint=settings.azure_ai_search_endpoint,
        credential=AzureKeyCredential(settings.azure_ai_search_api_key),
    )
