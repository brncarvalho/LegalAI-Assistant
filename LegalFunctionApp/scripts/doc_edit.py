# %%

from src.llm.clients import (
    get_openai_client,
    get_ai_search_client,
    get_model_config,
    get_ai_indexing_client,
)
from src.pipeline.clause_extraction_and_processing import (
    extract_contract_json,
    apply_page_overlap,
    filtrar_clausulas_por_numero,
)
from src.pipeline.reviewing import (
    review_clauses,
    filter_clauses_with_gpt4o,
    review_clauses_with_contract_context,
    create_original_and_revised_docs,
    create_temp_index,
    vectorize_and_upload,
    deduplicate_clauses,
)
from src.utils.models import PageOutput, PageReviewedOutput
import json
import uuid

from src.config.load_config import get_search_credentials

# %%
gpt_4o = get_openai_client("gpt_4o")
mini = get_openai_client("gpt_4o_mini")
search_client = get_ai_search_client()
search_index = get_ai_indexing_client()
model_cfg = get_model_config()
index_credentials = get_search_credentials()
# %%
# contract_json = extract_contract_json(r"C:\Users\bruno\Documents\pdf_files\claro.pdf")
contract_json = extract_contract_json(r"C:\Users\bruno\Downloads\nda_hpe.pdf", "layout")
# %%

# %%
print(contract_json[1])
# %%
new_chunks = apply_page_overlap(contract_json, overlap_pages=2)

# %%
new_chunks

# %%
extracted = filter_clauses_with_gpt4o(
    new_chunks, gpt_4o, PageOutput, get_model_config()["openai_models"]["gpt_4o"]
)
# %%
extracted
# %%
clean_clauses = deduplicate_clauses(extracted)
# %%
clean_clauses

# %%
reviewed_clauses = review_clauses(
    clean_clauses,
    gpt_4o,
    PageReviewedOutput,
    get_model_config()["openai_models"]["gpt_4o"],
    "contratada",
)

# %%
reviewed_clauses

# %%
dict_filtrado = filtrar_clausulas_por_numero(reviewed_clauses["reviewed_clauses"])
# %%
dict_filtrado

out_dir = r"C:\Users\Bruno\Documents"

create_original_and_revised_docs(dict_filtrado, out_dir, "nda_hpe.pdf")

# %%
