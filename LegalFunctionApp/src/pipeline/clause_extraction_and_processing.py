


from src.llm.clients import get_document_intelligence_client


from azure.ai.documentintelligence.models import DocumentContentFormat
import tiktoken
import re

# Initialize the Document Intelligence client
doc_client = get_document_intelligence_client()

def extract_contract_json(filepath, type='contract'):
    """
    Extracts and returns the analysis result of a contract document as JSON.

    Parameters:
        filepath (str): Path to the contract file to analyze.

    Returns:
        dict: The analysis result converted to a dictionary.
    """
    # Open the file in binary read mode

    if type == 'contract':
        with open(filepath, "rb") as f:
            # Begin analysis using the prebuilt contract model
            poller = doc_client.begin_analyze_document(
                model_id="prebuilt-contract", 
                body=f,
                output_content_format=DocumentContentFormat.TEXT
            )
            # Wait for the operation to complete and retrieve the result
            result = poller.result()
            # Convert the result to a dictionary and return
            return result.as_dict()
        
    elif type == 'layout':
        with open(filepath, "rb") as f:
            # Begin analysis using the prebuilt contract model
            poller = doc_client.begin_analyze_document(
                model_id="prebuilt-layout", 
                body=f,
                output_content_format=DocumentContentFormat.MARKDOWN
            )
            # Wait for the operation to complete and retrieve the result
            result = poller.result()
            # Convert the result to a dictionary and return

            chunks = []
            page_number = 1

            for page in result.pages: 
                content = result.content[page.spans[0]['offset']: page.spans[0]['offset'] + page.spans[0]['length']]
                chunks.append(content)
                
                page_number+=1


            return chunks








def chunk_contract_by_page(contract_json):
    """
    Splits the contract JSON into page-level chunks with page numbers and concatenated line content.

    Parameters:
        contract_json (dict): The JSON output from the contract analysis containing page data.

    Returns:
        list[dict]: A list of chunks, each with keys 'page_number' and 'content'.
    """
    chunks = []
    # Iterate over each page in the contract JSON
    for page in contract_json.get('pages', []):
        # Concatenate all line contents separated by newline
        content = "\n".join([line.get('content') for line in page.get('lines', [])])
        # Append the chunk dictionary to the list
        chunks.append({
            "page_number": page.get('pageNumber'),
            "content": content
        })
    # Return the list of page chunks
    return chunks




def apply_overlap_on_chunks(original_chunks, overlap=1):
    """
    Applies a simple overlapping context window by merging adjacent page contents.

    Parameters:
        original_chunks (list[dict]): List of page chunks from chunk_contract_by_page.
        overlap (int): Number of pages before and after to include for context.

    Returns:
        list[dict]: A new list of chunks with overlapping content.
    """
    # Extract just the content and page numbers for easier access
    page_contents = [chunk["content"] for chunk in original_chunks]
    page_numbers = [chunk["page_number"] for chunk in original_chunks]

    overlapped_chunks = []
    # Loop through each page index
    for i in range(len(original_chunks)):
        combined = []
        # Loop through offsets in the overlap window
        for offset in range(-overlap, overlap + 1):
            idx = i + offset
            # If the index is valid, add that page's content
            if 0 <= idx < len(page_contents):
                combined.append(page_contents[idx])
        # Join combined contents and store with the original page number
        overlapped_chunks.append({
            "page_number": page_numbers[i],
            "content": "\n".join(combined)
        })
    # Return the overlapped page chunks
    return overlapped_chunks




def apply_token_overlap_by_tokens(chunks, overlap_tokens=600, model_name="gpt-4o"):
    """
    Applies token-level overlap from the next page to each chunk for LLM input.

    Parameters:
        chunks (list[dict]): List of page chunks with 'page_number' and 'content'.
        overlap_tokens (int): Number of tokens to overlap from the next page.
        model_name (str): The name of the tokenizer model to use.

    Returns:
        list[dict]: A list of chunks with content extended by token overlap from the next page.
    """
    # Initialize tokenizer for the specified model
    tokenizer = tiktoken.encoding_for_model(model_name)
    overlapped_chunks = []

    # Iterate over chunks with index
    for i, chunk in enumerate(chunks):
        #current_content = chunk["content"]

        current_content = chunk

        # Determine overlap from next chunk if available
        if i + 1 < len(chunks):
            #next_content = chunks[i + 1]["content"]
            next_content = chunks[i + 1]
            next_tokens = tokenizer.encode(next_content)
            # Limit the slice to the requested number of tokens
            slice_end = min(overlap_tokens, len(next_tokens))
            next_overlap = tokenizer.decode(next_tokens[:slice_end])
        else:
            next_overlap = ""
        # Combine current content with the overlapped next content if any
        if next_overlap:
            combined = f"{current_content}\n\n{next_overlap}"
        else:
            combined = current_content
        # Append the combined content with page number
        overlapped_chunks.append({
            #"page_number": chunk["page_number"],
            "content": combined
        })
    return overlapped_chunks




def apply_page_overlap(chunks, overlap_pages=3):
    """
    Aplica overlap de páginas: para cada chunk (página), junta o conteúdo
    das próximas `overlap_pages` páginas inteiras.

    Parâmetros:
        chunks (list[dict]): Lista de dicts com 'page_number' e 'content'.
        overlap_pages (int): Quantas páginas seguintes incluir no overlap.

    Retorno:
        list[dict]: Cada chunk com 'content' estendido pelas próximas páginas.
    """
    overlapped = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        # Pega os conteúdos das próximas overlap_pages páginas
        next_contents = [
            chunks[j]
            for j in range(i+1, min(i+1 + overlap_pages, total))
        ]

        if next_contents:
            combined = chunk + "\n\n" + "\n\n".join(next_contents)
        else:
            combined = chunk

        overlapped.append({
            #"page_number": chunk["page_number"],
            "content": combined
        })

    return overlapped



def normalize_clause_number(raw: str) -> str:
    """
    Normalizes a raw clause number string by stripping whitespace and trailing dots.

    Parameters:
        raw (str): The raw clause number.

    Returns:
        str: The normalized clause number.
    """
    # Remove whitespace and trailing periods
    return re.sub(r"\.+$", "", raw.strip())





def merge_overlapped_clauses(extracted_pages: dict):
    """
    Merges overlapped clauses from multiple pages into a unique list.

    Parameters:
        extracted_pages (dict): A mapping of page numbers to data containing 'clauses'.

    Returns:
        list[dict]: A list of unique clauses with keys 'clause_number' and 'content'.
    """
    consolidated_clauses = {}
    # Iterate through each page and its clauses
    for page, data in extracted_pages.items():
        for clause in data["clauses"]:
            clause_number = clause["clause_number"]
            key = normalize_clause_number(clause_number)
            content = clause["content"].strip()
            # Store or replace with the longer content version
            if key not in consolidated_clauses or len(content) > len(consolidated_clauses[key]):
                consolidated_clauses[key] = content
    # Remove duplicates while preserving order
    seen = set()
    final_clauses = []
    for num, content in consolidated_clauses.items():
        if content not in seen:
            seen.add(content)
            final_clauses.append({
                "clause_number": num,
                "content": content
            })
    return final_clauses




def merge_overlapped_clauses_with_title(extracted_pages: dict):
    """
    Merges overlapped clauses including titles from multiple pages into a unique list.

    Parameters:
        extracted_pages (dict): A mapping of page numbers to data containing 'clauses'.

    Returns:
        list[dict]: A list of unique clauses with keys 'clause_title', 'clause_number', and 'content'.
    """
    consolidated_clauses = {}
    # Iterate through each page and its clauses
    for page, data in extracted_pages.items():
        for clause in data["clauses"]:
            clause_number = clause["clause_number"]
            content = clause["content"].strip()
            # Initialize or replace with the longer content version
            if clause_number not in consolidated_clauses:
                consolidated_clauses[clause_number] = content
            else:
                if len(content) > len(consolidated_clauses[clause_number]):
                    consolidated_clauses[clause_number] = content
    # Create final list including titles (note: original title extraction not provided)
    final_clauses = [{"clause_title": title, "clause_number": num, "content": txt}
                     for num, txt, title in consolidated_clauses.items()]
    return final_clauses



def filtrar_clausulas_por_numero(dict_clausulas):
    """
    Filters internal clause numbers in a nested clauses structure to match the main clause.

    Parameters:
        dict_clausulas (dict): Mapping of clause numbers to dicts with 'clauses' lists.

    Returns:
        dict: The updated mapping with normalized 'numero_da_clausula'.
    """

    for chave, valor in dict_clausulas.items():
        # Determine main clause number by stripping dots
        clausula_numero_principal = chave.strip('.')
        clausulas_internas = valor.get('clauses', [])
        # Normalize each internal clause number
        for clausula in clausulas_internas:
            if clausula['numero_da_clausula'].strip('.') != clausula_numero_principal:
                clausula['numero_da_clausula'] = clausula_numero_principal
    
    return dict_clausulas



def clause_key(num_str: str):
    """
    Converts a dot-separated numeric string into a tuple of integers for sorting.

    Parameters:
        num_str (str): The clause number string (e.g., '4.5.2').

    Returns:
        tuple[int]: A tuple of integers representing the clause hierarchy (e.g., (4,5,2)).
    """
    # Split the string on dots, filter out empty parts, convert to int
    parts = [p for p in num_str.split('.') if p]
    return tuple(int(p) for p in parts)