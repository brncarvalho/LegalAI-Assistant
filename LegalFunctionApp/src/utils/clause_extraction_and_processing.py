"""
Contract document extraction and clause processing.

Handles PDF extraction via Azure Document Intelligence and
clause chunking/overlap/normalization logic.
"""

import re


def apply_page_overlap(chunks, overlap_pages=3):
    """
    Apply page-level overlap: for each chunk, append content from the
    next `overlap_pages` pages to preserve cross-page context.

    Parameters:
        chunks (list[str]): List of page content strings.
        overlap_pages (int): How many subsequent pages to include.

    Returns:
        list[dict]: Each chunk with 'content' extended by subsequent pages.
    """
    overlapped = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        next_contents = [chunks[j] for j in range(i + 1, min(i + 1 + overlap_pages, total))]

        if next_contents:
            combined = chunk + "\n\n" + "\n\n".join(next_contents)
        else:
            combined = chunk

        overlapped.append({"content": combined})

    return overlapped


def normalize_clause_number(raw: str) -> str:
    """
    Normalize a clause number by stripping whitespace and trailing dots.

    Examples:
        "3.1." -> "3.1"
        " 4.2 " -> "4.2"
    """
    return re.sub(r"\.+$", "", raw.strip())


def normalize_clause_numbers(clauses_dict):
    """
    Normalize internal clause numbers to match their parent clause key.

    For each clause group, ensures all internal 'numero_da_clausula' values
    match the parent key (e.g., if key is "3.1", all clauses inside get "3.1").

    Parameters:
        clauses_dict (dict): Mapping of clause numbers to dicts with 'clauses' lists.

    Returns:
        dict: Updated mapping with normalized 'numero_da_clausula' values.
    """
    for key, value in clauses_dict.items():
        main_number = key.strip(".")
        internal_clauses = value.get("clauses", [])
        for clause in internal_clauses:
            if clause["numero_da_clausula"].strip(".") != main_number:
                clause["numero_da_clausula"] = main_number

    return clauses_dict
