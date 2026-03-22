"""
Clause deduplication logic.

Merges overlapping clauses that appear across multiple page chunks
(due to page overlap in the extraction phase).
"""

from src.pipeline.clause_extraction_and_processing import normalize_clause_number


def deduplicate_clauses(extracted_pages: dict) -> list[dict]:
    """
    Merge overlapping clauses from multiple pages into a unique list.

    When the same clause appears in multiple chunks (due to page overlap),
    keeps the longest version — more content means more complete extraction.

    Parameters:
        extracted_pages (dict): Dict with 'clauses' key containing page-indexed chunks:
            {
                'clauses': {
                    '0': {'page_number': int, 'clauses': [{clause_number, content}, ...]},
                    '1': {...},
                }
            }

    Returns:
        list[dict]: Unique clauses with 'clause_number' and 'content',
                    ordered by first appearance.
    """

    def normalize_spaces(text: str) -> str:
        return " ".join(text.split())

    raw_chunks = extracted_pages.get("clauses", {})
    page_list = list(raw_chunks.values())
    page_list.sort(key=lambda chunk: chunk.get("page_number", 0))

    consolidated: dict[str, str] = {}
    clause_order: list[str] = []

    for page_data in page_list:
        for clause in page_data.get("clauses", []):
            key = normalize_clause_number(clause["clause_number"])
            raw_content = clause["content"].strip()
            norm_content = normalize_spaces(raw_content)

            if key not in consolidated:
                consolidated[key] = raw_content
                clause_order.append(key)
            else:
                existing_norm = normalize_spaces(consolidated[key])
                if len(norm_content) > len(existing_norm):
                    consolidated[key] = raw_content

    return [
        {"clause_number": num, "content": consolidated[num]}
        for num in clause_order
    ]
