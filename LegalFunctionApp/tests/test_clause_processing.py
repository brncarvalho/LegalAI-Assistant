"""
Tests for clause extraction and processing functions.

These are pure functions (no network calls) — perfect for unit testing.
"""

from src.pipeline.clause_extraction_and_processing import (
    apply_page_overlap,
    normalize_clause_number,
    normalize_clause_numbers,
)


class TestNormalizeClauseNumber:
    """Tests for normalize_clause_number — strips whitespace and trailing dots."""

    def test_trailing_dot(self):
        assert normalize_clause_number("3.1.") == "3.1"

    def test_multiple_trailing_dots(self):
        assert normalize_clause_number("4.2...") == "4.2"

    def test_whitespace(self):
        assert normalize_clause_number("  5.3  ") == "5.3"

    def test_whitespace_and_dots(self):
        assert normalize_clause_number(" 6.1. ") == "6.1"

    def test_single_number(self):
        assert normalize_clause_number("7") == "7"

    def test_deeply_nested(self):
        assert normalize_clause_number("28.2.1.") == "28.2.1"

    def test_already_clean(self):
        assert normalize_clause_number("3.1") == "3.1"


class TestNormalizeClauseNumbers:
    """Tests for normalize_clause_numbers — aligns internal numbers to parent key."""

    def test_mismatched_number_gets_corrected(self, sample_reviewed_clauses):
        result = normalize_clause_numbers(sample_reviewed_clauses)

        # "4.2" should be corrected to "4" (matching key "4.")
        clause = result["4."]["clauses"][0]
        assert clause["numero_da_clausula"] == "4"

    def test_matching_number_stays_unchanged(self, sample_reviewed_clauses):
        result = normalize_clause_numbers(sample_reviewed_clauses)

        # "3.1." stripped to "3.1" matches key "3.1" stripped to "3.1"
        # so the original value "3.1." is preserved (not corrected)
        clause = result["3.1"]["clauses"][0]
        assert clause["numero_da_clausula"] == "3.1."

    def test_returns_same_dict(self, sample_reviewed_clauses):
        result = normalize_clause_numbers(sample_reviewed_clauses)
        assert result is sample_reviewed_clauses  # mutates in place

    def test_empty_dict(self):
        result = normalize_clause_numbers({})
        assert result == {}


class TestApplyPageOverlap:
    """Tests for apply_page_overlap — merges content from subsequent pages."""

    def test_overlap_extends_content(self):
        chunks = ["Page 1 content", "Page 2 content", "Page 3 content"]
        result = apply_page_overlap(chunks, overlap_pages=1)

        assert len(result) == 3
        assert "Page 1 content" in result[0]["content"]
        assert "Page 2 content" in result[0]["content"]

    def test_last_page_has_no_overlap(self):
        chunks = ["Page 1", "Page 2", "Page 3"]
        result = apply_page_overlap(chunks, overlap_pages=2)

        # Last page should only contain its own content
        assert result[2]["content"] == "Page 3"

    def test_overlap_of_two_pages(self):
        chunks = ["A", "B", "C", "D"]
        result = apply_page_overlap(chunks, overlap_pages=2)

        # First chunk should contain A + B + C
        assert "A" in result[0]["content"]
        assert "B" in result[0]["content"]
        assert "C" in result[0]["content"]
        assert "D" not in result[0]["content"]

    def test_single_page(self):
        chunks = ["Only page"]
        result = apply_page_overlap(chunks, overlap_pages=3)

        assert len(result) == 1
        assert result[0]["content"] == "Only page"

    def test_empty_list(self):
        result = apply_page_overlap([], overlap_pages=2)
        assert result == []
