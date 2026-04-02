"""
Text embedding generation using Azure OpenAI.
"""

from openai import AzureOpenAI

from src.config.settings import settings


class EmbeddingService:
    def __init__(self):
        self.client = AzureOpenAI(
            api_version=settings.api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
        )

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Parameters:
            client: An initialized AzureOpenAI client configured for embeddings.
            text (str): The input text to embed.

        Returns:
            list[float]: The embedding vector.
        """

        response = self.client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )

        return response.data[0].embedding
