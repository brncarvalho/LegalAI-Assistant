"""
Model configuration loader.

Loads LLM tuning parameters (temperature, max_tokens, deployment names)
from model_config.yaml. These are NOT secrets — they're model behavior settings
that belong in a version-controlled config file.

For secrets and endpoints, see settings.py (Pydantic BaseSettings).
"""

import os

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "model_config.yaml")


def get_model_config() -> dict:
    """Load and return model configuration from the YAML file."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
