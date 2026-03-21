"""
Text embedding generation using Azure OpenAI.
"""

from src.config.load_config import get_model_config


def generate_embedding(client, text):
    """
    Generate an embedding vector for the given text.

    Parameters:
        client: An initialized AzureOpenAI client configured for embeddings.
        text (str): The input text to embed.

    Returns:
        list[float]: The embedding vector.
    """
    model_config = get_model_config()["openai_models"]["embeddings"]

    response = client.embeddings.create(
        model=model_config["deployment"],
        input=text,
    )

    return response.data[0].embedding
