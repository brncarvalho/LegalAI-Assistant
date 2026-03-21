"""
Reusable retry logic for LLM API calls.

Why a separate module? Retry is a cross-cutting concern — it's used by
reviewing, filtering, and any future LLM call. Putting it in its own
module means you only change retry behavior in one place.
"""

import logging
import time

from azure.core.exceptions import HttpResponseError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF = 5  # seconds


def safe_parse_with_retry(client, messages, response_format, model_config):
    """
    Send messages to the LLM with exponential backoff retry on HttpResponseError.

    Parameters:
        client: AzureOpenAI client.
        messages: Chat messages list.
        response_format: Pydantic model for structured output parsing.
        model_config (dict): Must contain 'max_tokens', 'temperature', 'top_p', 'deployment'.

    Returns:
        The parsed LLM response object.

    Raises:
        HttpResponseError: If all retry attempts are exhausted.
    """
    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.beta.chat.completions.parse(
                messages=messages,
                response_format=response_format,
                max_tokens=model_config["max_tokens"],
                temperature=model_config["temperature"],
                top_p=model_config["top_p"],
                model=model_config["deployment"],
            )
        except HttpResponseError as e:
            code = getattr(e, "status_code", None)
            logger.warning(
                "[LLM Retry] Attempt %d/%d failed (status=%s): %s",
                attempt, MAX_RETRIES, code, e,
            )
            if attempt == MAX_RETRIES:
                logger.error("All %d retry attempts exhausted.", MAX_RETRIES)
                raise
            logger.info("Waiting %ds before next attempt...", backoff)
            time.sleep(backoff)
            backoff *= 2
