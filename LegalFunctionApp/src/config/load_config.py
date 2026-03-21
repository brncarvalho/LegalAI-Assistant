import os  # for filesystem path operations
import yaml  # for parsing YAML configuration files
from dotenv import load_dotenv  # to load environment variables from a .env file

load_dotenv()  # load environment variables into the process environment

# path to the model configuration YAML file, located next to this script
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "model_config.yaml")


def get_model_config():
    """
    Load and return the model configuration from the YAML file.

    Reads the YAML file at CONFIG_PATH, parses its contents, and returns
    the resulting dictionary of configuration parameters.
    """
    # open the YAML config file with UTF-8 encoding
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        # parse the YAML and return as a Python dict
        return yaml.safe_load(f)


def get_openai_credentials():
    """
    Retrieve Azure OpenAI endpoint and API key from environment variables.

    Returns a dict with:
      - 'endpoint': the AZURE_OPENAI_ENDPOINT value
      - 'key': the AZURE_OPENAI_API_KEY value
    """
    # construct and return credentials dict for Azure OpenAI
    return {
        "endpoint": os.getenv("AZURE_OPENAI_ENDPOINT"),  # endpoint URL for Azure OpenAI
        "key": os.getenv("AZURE_OPENAI_API_KEY")         # API key for Azure OpenAI
    }


def get_embeddings_credentials():
    """
    Retrieve embeddings service endpoint and API key from environment variables.

    Returns a dict with:
      - 'endpoint': the EMBEDDINGS_OPENAI_ENDPOINT value
      - 'key': the EMBEDDINGS_OPENAI_API_KEY value
    """
    # construct and return credentials dict for embeddings service
    return {
        "endpoint": os.getenv("EMBEDDINGS_OPENAI_ENDPOINT"),  # endpoint URL for embeddings
        "key": os.getenv("EMBEDDINGS_OPENAI_API_KEY")         # API key for embeddings
    }


def get_doc_intelligence_credentials():
    """
    Retrieve Azure Document Intelligence endpoint and API key from environment variables.

    Returns a dict with:
      - 'endpoint': the AZURE_AI_DOC_INTELLIGENCE_ENDPOINT value
      - 'key': the AZURE_AI_DOC_INTELLIGENCE_API_KEY value
    """
    # construct and return credentials dict for Document Intelligence
    return {
        "endpoint": os.getenv("AZURE_AI_DOC_INTELLIGENCE_ENDPOINT"),  # endpoint URL for Doc Intelligence
        "key": os.getenv("AZURE_AI_DOC_INTELLIGENCE_API_KEY")         # API key for Doc Intelligence
    }


def get_search_credentials():
    """
    Retrieve Azure Cognitive Search endpoint and API key from environment variables.

    Returns a dict with:
      - 'endpoint': the AZURE_AI_SEARCH_ENDPOINT value
      - 'key': the AZURE_AI_SEACH_API_KEY value
    """
    # construct and return credentials dict for Azure Search
    return {
        "endpoint": os.getenv("AZURE_AI_SEARCH_ENDPOINT"),  # endpoint URL for Azure Search
        "key": os.getenv("AZURE_AI_SEACH_API_KEY")         # API key for Azure Search
    }

