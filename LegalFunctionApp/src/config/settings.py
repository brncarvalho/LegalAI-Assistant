"""
Centralized application settings using Pydantic BaseSettings.

Why BaseSettings instead of os.getenv()?
- Validates ALL env vars at startup (fail fast, not 3 functions deep)
- Type-safe: IDE autocomplete, no typos like "AZURE_AI_SEACH_API_KEY"
- Single source of truth: one class, not 4 scattered functions
- Testable: you can create Settings(azure_openai_endpoint="fake", ...) in tests

Usage:
    settings = Settings()          # loads from environment / .env file
    settings.azure_openai_endpoint # typed, validated, no None surprises
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All external configuration for the Norma application.

    Pydantic automatically maps UPPER_CASE env vars to lower_case fields.
    Example: env var AZURE_OPENAI_ENDPOINT -> settings.azure_openai_endpoint
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # don't fail on extra env vars (Azure Functions sets many)
    )

    # ── Azure OpenAI (main LLM calls) ──────────────────────────────
    azure_openai_endpoint: str
    azure_openai_api_key: str

    # ── Azure OpenAI Embeddings (separate deployment) ──────────────
    embeddings_openai_endpoint: str
    embeddings_openai_api_key: str

    # ── Azure Document Intelligence (PDF extraction) ───────────────
    azure_ai_doc_intelligence_endpoint: str
    azure_ai_doc_intelligence_api_key: str

    # ── Azure AI Search (vector search) ────────────────────────────
    azure_ai_search_endpoint: str
    azure_ai_search_api_key: str

    # ── Azure Blob Storage ─────────────────────────────────────────
    azure_web_jobs_storage: str

    # ── Azure OpenAI Resource URL (for search vectorizer) ──────────
    # This was previously hardcoded in reviewing.py and indexing.py
    azure_openai_resource_url: str
