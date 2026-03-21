"""
Token usage tracking for LLM API calls.

Why a class and not a function?
Because token counts are MUTABLE STATE that accumulates across multiple
LLM calls within a single pipeline run. A class encapsulates the counters
and the operations on them — you can't accidentally forget to update one.

Compare:
    # Without class (easy to forget one counter):
    total_prompt += response.usage.prompt_tokens
    total_completion += response.usage.completion_tokens
    total_tokens += response.usage.total_tokens

    # With class (one call, can't miss anything):
    tracker.track(response)
"""


class TokenTracker:
    """
    Accumulates token usage across multiple LLM API calls.

    Usage:
        tracker = TokenTracker()
        for clause in clauses:
            response = client.beta.chat.completions.parse(...)
            tracker.track(response)
        return tracker.usage  # {"prompt": 1234, "completion": 567, "total": 1801}
    """

    def __init__(self):
        self.prompt = 0
        self.completion = 0
        self.total = 0

    def track(self, response) -> None:
        """
        Record token usage from an LLM API response.

        Parameters:
            response: OpenAI API response with a .usage attribute containing
                      prompt_tokens, completion_tokens, and total_tokens.
        """
        self.prompt += response.usage.prompt_tokens
        self.completion += response.usage.completion_tokens
        self.total += response.usage.total_tokens

    @property
    def usage(self) -> dict:
        """Return usage as a dict matching the pipeline's expected format."""
        return {
            "prompt": self.prompt,
            "completion": self.completion,
            "total": self.total,
        }
