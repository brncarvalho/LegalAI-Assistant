from src.llm.clients import get_embeddings_openai_client
from src.config.load_config import get_model_config, get_embeddings_credentials

# Load and cache embeddings credentials (endpoint & key) from environment
credentials = get_embeddings_credentials()


def generate_embedding(text):

    """
    Generate and return an embedding vector for the given text using Azure OpenAI.

    Steps:
      1. Load the embeddings model configuration (e.g., deployment name).
      2. Instantiate an embeddings client.
      3. Call the Azure OpenAI embeddings API.
      4. Return the embedding vector from the first response entry.

    Parameters:
        text (str): The input text to embed.

    Returns:
        List[float]: The embedding vector for the input text.
    """
    # Retrieve the embeddings model settings from model_config.yaml
    model_config = get_model_config()["openai_models"]["embeddings"]
    # Instantiate the Azure OpenAI client configured for embeddings
    client = get_embeddings_openai_client("embeddings")
    # Call the embeddings endpoint with the specified model and input text
    response = client.embeddings.create(
        model=model_config["deployment"],   # deployment name as defined in config
        input=text              # the text string to generate embeddings for
    )

    # Extract and return the embedding vector from the API response
    return response.data[0].embedding