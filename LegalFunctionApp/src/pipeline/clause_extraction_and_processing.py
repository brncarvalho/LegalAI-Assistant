"""
Contract document extraction and clause processing.

Handles PDF extraction via Azure Document Intelligence and
clause chunking/overlap/normalization logic.
"""

import re
from azure.ai.documentintelligence.models import DocumentContentFormat


def extract_contract_json(doc_client, filepath, type='contract'):
    """
    Extract text from a contract PDF using Azure Document Intelligence.

    Parameters:
        doc_client: An initialized DocumentIntelligenceClient.
        filepath (str): Path to the PDF file.
        type (str): 'contract' for prebuilt-contract model, 'layout' for prebuilt-layout.

    Returns:
        dict or list: Full analysis dict (contract mode) or list of page content strings (layout mode).
    """
    if type == 'contract':
        with open(filepath, "rb") as f:
            poller = doc_client.begin_analyze_document(
                model_id="prebuilt-contract",
                body=f,
                output_content_format=DocumentContentFormat.TEXT,
            )
            result = poller.result()
            return result.as_dict()

    elif type == 'layout':
        with open(filepath, "rb") as f:
            poller = doc_client.begin_analyze_document(
                model_id="prebuilt-layout",
                body=f,
                output_content_format=DocumentContentFormat.MARKDOWN,
            )
            result = poller.result()

            chunks = []
            for page in result.pages:
                content = result.content[
                    page.spans[0]['offset']:
                    page.spans[0]['offset'] + page.spans[0]['length']
                ]
                chunks.append(content)

            return chunks


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
        next_contents = [
            chunks[j]
            for j in range(i + 1, min(i + 1 + overlap_pages, total))
        ]

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
        main_number = key.strip('.')
        internal_clauses = value.get('clauses', [])
        for clause in internal_clauses:
            if clause['numero_da_clausula'].strip('.') != main_number:
                clause['numero_da_clausula'] = main_number

    return clauses_dict
