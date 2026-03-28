# %%

from LegalFunctionApp.models.models import PageOutput, PageReviewedOutput

from src.config.load_config import get_search_credentials
from src.llm.clients import (
    get_ai_indexing_client,
    get_ai_search_client,
    get_model_config,
    get_openai_client,
)
from src.pipeline.clause_extraction_and_processing import (
    apply_page_overlap,
    extract_contract_json,
    normalize_clause_numbers,
)
from src.pipeline.reviewing import (
    create_original_and_revised_docs,
    deduplicate_clauses,
    filter_clauses_with_gpt4o,
    review_clauses,
)

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
dict_filtrado = normalize_clause_numbers(reviewed_clauses["reviewed_clauses"])
# %%
dict_filtrado

out_dir = r"C:\Users\Bruno\Documents"

create_original_and_revised_docs(dict_filtrado, out_dir, "nda_hpe.pdf")

# %%
