"""
Tests for safe_parse_with_retry — uses mocking to simulate LLM failures.

This demonstrates testing code that makes external API calls:
you mock the client so tests don't need a real Azure connection.
"""

from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import HttpResponseError

from src.utils.retry import safe_parse_with_retry


@pytest.fixture
def model_config():
    return {
        "max_tokens": 1000,
        "temperature": 0.0,
        "top_p": 1.0,
        "deployment": "gpt-4o",
    }


@pytest.fixture
def mock_client():
    return MagicMock()


class TestSafeParseWithRetry:

    def test_success_on_first_try(self, mock_client, model_config):
        expected = MagicMock()
        mock_client.beta.chat.completions.parse.return_value = expected

        result = safe_parse_with_retry(
            mock_client, [{"role": "user", "content": "test"}], str, model_config
        )

        assert result is expected
        assert mock_client.beta.chat.completions.parse.call_count == 1

    @patch("src.utils.retry.time.sleep")  # don't actually sleep in tests
    def test_retries_on_http_error(self, mock_sleep, mock_client, model_config):
        expected = MagicMock()
        mock_client.beta.chat.completions.parse.side_effect = [
            HttpResponseError("Server error"),
            expected,
        ]

        result = safe_parse_with_retry(
            mock_client, [{"role": "user", "content": "test"}], str, model_config
        )

        assert result is expected
        assert mock_client.beta.chat.completions.parse.call_count == 2
        mock_sleep.assert_called_once()

    @patch("src.utils.retry.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep, mock_client, model_config):
        mock_client.beta.chat.completions.parse.side_effect = HttpResponseError(
            "Server error"
        )

        with pytest.raises(HttpResponseError):
            safe_parse_with_retry(
                mock_client, [{"role": "user", "content": "test"}], str, model_config
            )

        assert mock_client.beta.chat.completions.parse.call_count == 3  # MAX_RETRIES

    @patch("src.utils.retry.time.sleep")
    def test_exponential_backoff(self, mock_sleep, mock_client, model_config):
        mock_client.beta.chat.completions.parse.side_effect = [
            HttpResponseError("Error 1"),
            HttpResponseError("Error 2"),
            MagicMock(),  # success on 3rd try
        ]

        safe_parse_with_retry(
            mock_client, [{"role": "user", "content": "test"}], str, model_config
        )

        # First backoff: 5s, second: 10s (5 * 2)
        calls = mock_sleep.call_args_list
        assert calls[0][0][0] == 5
        assert calls[1][0][0] == 10
