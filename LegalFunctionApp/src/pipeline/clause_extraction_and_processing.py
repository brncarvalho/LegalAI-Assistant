"""
Contract document extraction and clause processing.

Handles PDF extraction via Azure Document Intelligence and
clause chunking/overlap/normalization logic.
"""

from azure.ai.documentintelligence.models import DocumentContentFormat
import tiktoken
import re


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


def apply_token_overlap_by_tokens(chunks, overlap_tokens=600, model_name="gpt-4o"):
    """
    Apply token-level overlap from the next page to each chunk.

    Parameters:
        chunks (list[str]): List of page content strings.
        overlap_tokens (int): Number of tokens to overlap from the next page.
        model_name (str): Tokenizer model name.

    Returns:
        list[dict]: Chunks with content extended by token overlap.
    """
    tokenizer = tiktoken.encoding_for_model(model_name)
    overlapped_chunks = []

    for i, chunk in enumerate(chunks):
        current_content = chunk

        if i + 1 < len(chunks):
            next_content = chunks[i + 1]
            next_tokens = tokenizer.encode(next_content)
            slice_end = min(overlap_tokens, len(next_tokens))
            next_overlap = tokenizer.decode(next_tokens[:slice_end])
        else:
            next_overlap = ""

        if next_overlap:
            combined = f"{current_content}\n\n{next_overlap}"
        else:
            combined = current_content

        overlapped_chunks.append({"content": combined})

    return overlapped_chunks


def normalize_clause_number(raw: str) -> str:
    """
    Normalize a clause number by stripping whitespace and trailing dots.

    Examples:
        "3.1." -> "3.1"
        " 4.2 " -> "4.2"
    """
    return re.sub(r"\.+$", "", raw.strip())


def merge_overlapped_clauses(extracted_pages: dict):
    """
    Merge overlapped clauses from multiple pages into a deduplicated list.
    Keeps the longest version of each clause.

    Parameters:
        extracted_pages (dict): Mapping of page numbers to dicts with 'clauses' lists.

    Returns:
        list[dict]: Unique clauses with 'clause_number' and 'content'.
    """
    consolidated_clauses = {}
    for page, data in extracted_pages.items():
        for clause in data["clauses"]:
            clause_number = clause["clause_number"]
            key = normalize_clause_number(clause_number)
            content = clause["content"].strip()
            if key not in consolidated_clauses or len(content) > len(consolidated_clauses[key]):
                consolidated_clauses[key] = content

    seen = set()
    final_clauses = []
    for num, content in consolidated_clauses.items():
        if content not in seen:
            seen.add(content)
            final_clauses.append({"clause_number": num, "content": content})
    return final_clauses


def filtrar_clausulas_por_numero(dict_clausulas):
    """
    Normalize internal clause numbers to match their parent clause key.

    Parameters:
        dict_clausulas (dict): Mapping of clause numbers to dicts with 'clauses' lists.

    Returns:
        dict: Updated mapping with normalized 'numero_da_clausula' values.
    """
    for chave, valor in dict_clausulas.items():
        clausula_numero_principal = chave.strip('.')
        clausulas_internas = valor.get('clauses', [])
        for clausula in clausulas_internas:
            if clausula['numero_da_clausula'].strip('.') != clausula_numero_principal:
                clausula['numero_da_clausula'] = clausula_numero_principal

    return dict_clausulas


def clause_key(num_str: str):
    """
    Convert a dot-separated clause number to a sortable tuple.

    Examples:
        "4.5.2" -> (4, 5, 2)
        "3" -> (3,)
    """
    parts = [p for p in num_str.split('.') if p]
    return tuple(int(p) for p in parts)
