"""
Tests for TokenTracker — the OOP example.

Shows how classes with state are easy to test:
create an instance, call methods, assert state.
"""

from unittest.mock import MagicMock

from src.utils.token_tracker import TokenTracker


class TestTokenTracker:
    """Tests for the TokenTracker class."""

    def test_initial_state_is_zero(self):
        tracker = TokenTracker()
        assert tracker.usage == {"prompt": 0, "completion": 0, "total": 0}

    def test_track_single_response(self):
        tracker = TokenTracker()

        response = MagicMock()
        response.usage.prompt_tokens = 100
        response.usage.completion_tokens = 50
        response.usage.total_tokens = 150

        tracker.track(response)

        assert tracker.usage == {"prompt": 100, "completion": 50, "total": 150}

    def test_track_accumulates_across_calls(self):
        tracker = TokenTracker()

        for i in range(3):
            response = MagicMock()
            response.usage.prompt_tokens = 10
            response.usage.completion_tokens = 5
            response.usage.total_tokens = 15
            tracker.track(response)

        assert tracker.usage == {"prompt": 30, "completion": 15, "total": 45}

    def test_usage_returns_dict(self):
        tracker = TokenTracker()
        result = tracker.usage

        assert isinstance(result, dict)
        assert set(result.keys()) == {"prompt", "completion", "total"}
