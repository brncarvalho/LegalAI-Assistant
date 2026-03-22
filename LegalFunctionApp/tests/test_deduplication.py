"""
Tests for clause deduplication logic.
"""

from src.pipeline.deduplication import deduplicate_clauses


class TestDeduplicateClauses:
    """Tests for deduplicate_clauses — merges overlapping clauses across pages."""

    def test_keeps_longer_version(self, sample_extracted_pages):
        result = deduplicate_clauses(sample_extracted_pages)

        # Clause 3.1 appears in both pages — should keep the longer version
        clause_31 = next(c for c in result if c["clause_number"] == "3.1")
        assert "more details" in clause_31["content"]

    def test_preserves_unique_clauses(self, sample_extracted_pages):
        result = deduplicate_clauses(sample_extracted_pages)

        numbers = [c["clause_number"] for c in result]
        assert "3.2" in numbers
        assert "4.1" in numbers

    def test_no_duplicates(self, sample_extracted_pages):
        result = deduplicate_clauses(sample_extracted_pages)

        numbers = [c["clause_number"] for c in result]
        assert len(numbers) == len(set(numbers))

    def test_preserves_first_appearance_order(self, sample_extracted_pages):
        result = deduplicate_clauses(sample_extracted_pages)

        numbers = [c["clause_number"] for c in result]
        # 3.1 and 3.2 appear on page 1, 4.1 on page 2
        assert numbers.index("3.1") < numbers.index("4.1")

    def test_empty_input(self):
        result = deduplicate_clauses({"clauses": {}})
        assert result == []

    def test_single_page(self):
        data = {
            "clauses": {
                "0": {
                    "page_number": 1,
                    "clauses": [
                        {"clause_number": "1.1", "content": "Only clause"},
                    ],
                }
            }
        }
        result = deduplicate_clauses(data)
        assert len(result) == 1
        assert result[0]["content"] == "Only clause"
