"""
Azure Durable Functions orchestration for Norma legal contract review.

This is the entry point. It creates Settings once and passes dependencies
(clients, config) down to pipeline functions — never at module level.
"""

import os
import json
import tempfile
import logging
import calendar
from datetime import datetime, timezone
import shutil
from pathlib import Path
import uuid

import azure.functions as func
import azure.durable_functions as df
from azure.storage.blob import BlobServiceClient

from src.config.settings import Settings
from src.config.load_config import get_model_config
from src.llm.clients import (
    get_openai_client,
    get_ai_search_client,
    get_document_intelligence_client,
)
from src.pipeline.clause_extraction_and_processing import (
    extract_contract_json,
    apply_page_overlap,
    filtrar_clausulas_por_numero,
)
from src.pipeline.reviewing import (
    deduplicate_clauses,
    filter_clauses_with_gpt4o,
    review_clauses,
    create_original_and_revised_docs,
)
from src.utils.models import PageOutput, PageReviewedOutput

logging.basicConfig(level=logging.INFO)

# Initialize the Durable Functions app
df_app = df.DFApp()


@df_app.blob_trigger(
    arg_name="blob",
    path="contracts-container/{name}.pdf",
    connection="AzureWebJobsStorage",
)
@df_app.durable_client_input(client_name="starter")
async def blob_start(blob: func.InputStream, starter: df.DurableOrchestrationClient):
    """
    Triggered when a new PDF is uploaded to 'contracts-container'.
    Starts the durable orchestration with the blob filename as input.
    """
    filename = blob.name.split("/")[-1]
    logging.info("[blob_start] New PDF arrived: %s", filename)

    instance_id = await starter.start_new(
        "Orchestrator", client_input={"blob_name": filename}
    )
    logging.info("[blob_start] Orchestration started: %s", instance_id)


@df_app.orchestration_trigger(context_name="context")
def Orchestrator(context: df.DurableOrchestrationContext):
    """
    Durable orchestrator coordinating the full contract review workflow.

    Steps:
      1. Extract raw JSON from PDF
      2. Filter clauses (parallel)
      3. Review clauses (parallel)
      4. Generate Word documents
      5. Record usage statistics
    """
    payload = context.get_input()
    logging.info("[Orchestrator] Received payload: %s", payload)

    blob_name = payload["blob_name"]
    stem = Path(blob_name).stem
    maybe_party = stem.rsplit("-", 1)[-1].lower() if "-" in stem else None
    party = maybe_party if maybe_party in {"contratante", "contratada"} else None
    logging.info("[Orchestrator] Detected party: %s", party)

    # 1. Extract raw JSON from PDF
    raw_info = yield context.call_activity("ExtractAndSaveActivity", payload)
    logging.info("[Orchestrator] Raw JSON written to blob: %s", raw_info['raw_blob'])

    extracted_blob = raw_info["raw_blob"]
    extracted_clauses_array = yield context.call_activity(
        "DownloadJsonArrayActivity",
        {"blob": extracted_blob, "container_name": "output"},
    )

    chunk_size = 5
    extracted_chunks = [
        extracted_clauses_array[i : i + chunk_size]
        for i in range(0, len(extracted_clauses_array), chunk_size)
    ]

    tasks = [
        context.call_activity("FilterClausesActivity", chunk)
        for chunk in extracted_chunks
    ]
    partial_results = yield context.task_all(tasks)

    logging.info(
        "[Orchestrator] Filter partial_results: %s",
        [len(r) for r in partial_results],
    )

    total_usage = {"prompt": 0, "completion": 0, "total": 0}

    extracted_merged: list[dict] = []
    for part in partial_results:
        extracted_merged.extend(part["filtered_blob"])
        total_usage["prompt"] += part["usage"]["prompt"]
        total_usage["completion"] += part["usage"]["completion"]
        total_usage["total"] += part["usage"]["total"]

    logging.info("[Orchestrator] Merged total: %d clauses", len(extracted_merged))

    extracted_merged_blob_info = yield context.call_activity(
        "SaveJsonArrayActivity",
        {
            "map": extracted_merged,
            "base_name": Path(extracted_blob).stem,
            "container_name": "extracted-clauses",
        },
    )

    # 3. Download filtered clauses
    filtered_blob = extracted_merged_blob_info["reviewed_blob"]
    clauses_array = yield context.call_activity(
        "DownloadJsonArrayActivity",
        {"blob": filtered_blob, "container_name": "extracted-clauses"},
    )

    logging.info(
        "[Orchestrator] Downloaded %d clauses for review", len(clauses_array)
    )

    # Split into chunks for parallel review
    chunk_size = 5
    chunks = [
        clauses_array[i : i + chunk_size]
        for i in range(0, len(clauses_array), chunk_size)
    ]

    logging.info("[Orchestrator] Split into %d chunks of up to %d", len(chunks), chunk_size)

    # 4. Parallel review
    tasks = [
        context.call_activity(
            "ReviewClausesChunkActivity", {"chunk": chunk, "party": party}
        )
        for chunk in chunks
    ]

    partial_results = yield context.task_all(tasks)

    merged: dict[str, dict] = {}
    for part in partial_results:
        merged.update(part["reviewed_clauses"])
        total_usage["prompt"] += part["usage"]["prompt"]
        total_usage["completion"] += part["usage"]["completion"]
        total_usage["total"] += part["usage"]["total"]

    logging.info("[Orchestrator] Merged total: %d reviewed clauses", len(merged))

    merged_blob_info = yield context.call_activity(
        "SaveJsonArrayActivity",
        {
            "map": merged,
            "base_name": Path(filtered_blob).stem,
            "container_name": "reviewed-clauses",
        },
    )

    # 5. Generate reviewed document
    final_doc = yield context.call_activity(
        "CreateReviewedDocumentActivity", merged_blob_info
    )

    # Build usage metadata
    contract_name = Path(merged_blob_info["reviewed_blob"]).name.split(".", 1)[0]
    now = datetime.now(timezone.utc)
    month_name = calendar.month_name[now.month]
    month_year = now.strftime("%m-%Y")

    usage_blob = yield context.call_activity(
        "SaveUsageActivity",
        {
            "base_name": Path(filtered_blob).stem,
            "contract_name": contract_name,
            "timestamp": now.isoformat(),
            "month_year": month_year,
            "year": now.year,
            "month": month_name,
            "prompt": total_usage["prompt"],
            "completion": total_usage["completion"],
            "total": total_usage["total"],
        },
    )

    return {**final_doc, "usage_blob": usage_blob["blob_name"]}


# ─── Activities ──────────────────────────────────────────────────────────────
# Each activity creates its own clients from Settings.
# This is dependency injection: the activity controls what it needs.


def _get_settings() -> Settings:
    """Create Settings from environment. Called per-activity, not at module level."""
    return Settings()


def _get_storage() -> BlobServiceClient:
    """Create a BlobServiceClient from the storage connection string."""
    return BlobServiceClient.from_connection_string(
        _get_settings().azure_web_jobs_storage
    )


@df_app.activity_trigger(input_name="payload")
def ExtractAndSaveActivity(payload: dict) -> dict:
    """
    Download a PDF from blob storage, extract text as JSON chunks,
    apply page overlap, and save the raw JSON back to blob storage.
    """
    blob_name = payload["blob_name"]
    logging.info("[ExtractAndSaveActivity] Start extracting '%s'", blob_name)

    settings = _get_settings()
    storage = BlobServiceClient.from_connection_string(settings.azure_web_jobs_storage)
    container = storage.get_container_client("contracts-container")

    downloader = container.download_blob(blob_name)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(downloader.readall())
        tmp.flush()
        pdf_path = tmp.name

    doc_client = get_document_intelligence_client(settings)
    contract_json = extract_contract_json(doc_client, pdf_path, "layout")
    chunks = apply_page_overlap(contract_json, overlap_pages=2)

    logging.info(
        "[ExtractAndSaveActivity] Extracted and overlapped %d chunks", len(chunks)
    )

    raw_blob = blob_name.rsplit(".", 1)[0] + ".json"
    raw_container = storage.get_container_client("output")
    raw_container.upload_blob(
        name=raw_blob, data=json.dumps(chunks, ensure_ascii=False), overwrite=True
    )
    logging.info("[ExtractAndSaveActivity] Raw JSON saved as '%s'", raw_blob)

    return {"raw_blob": raw_blob}


@df_app.activity_trigger(input_name="blobInfo")
def FilterClausesActivity(blobInfo: list) -> dict:
    """
    Filter and extract clauses via GPT-4o, then deduplicate overlapping clauses.
    """
    chunks = blobInfo

    settings = _get_settings()
    client = get_openai_client(settings, "gpt_4o")
    model_cfg = get_model_config()["openai_models"]["gpt_4o"]

    filtered = filter_clauses_with_gpt4o(chunks, client, PageOutput, model_cfg)
    clean_clauses = deduplicate_clauses(filtered)

    usage = filtered["usage"]
    logging.info("[FilterClausesActivity] Filtered down to %d clauses", len(filtered))

    return {"filtered_blob": clean_clauses, "usage": usage}


@df_app.activity_trigger(input_name="clauseschunk")
def ReviewClausesChunkActivity(clauseschunk: dict) -> dict:
    """
    Review a chunk of clauses via GPT-4o with Azure Search context,
    normalize numbering, and assign UUIDs.
    """
    if isinstance(clauseschunk, dict):
        chunk = clauseschunk.get("chunk", [])
        party = clauseschunk.get("party")
    else:
        chunk = clauseschunk
        party = None

    settings = _get_settings()
    client = get_openai_client(settings, "gpt_4o")
    search_client = get_ai_search_client(settings)
    model_cfg = get_model_config()["openai_models"]["gpt_4o"]

    reviewed_clauses = review_clauses(
        chunk, client, search_client, PageReviewedOutput, model_cfg, party
    )

    filtered_by_numbers = filtrar_clausulas_por_numero(
        reviewed_clauses["reviewed_clauses"]
    )

    for page_key, page in filtered_by_numbers.items():
        for clause in page["clauses"]:
            clause["id"] = str(uuid.uuid4())

    usage = reviewed_clauses["usage"]
    return {"reviewed_clauses": filtered_by_numbers, "usage": usage}


@df_app.activity_trigger(input_name="blobInfo")
def CreateReviewedDocumentActivity(blobInfo: dict) -> dict:
    """
    Download reviewed clauses JSON, create original & revised Word docs,
    and upload both to blob storage.
    """
    reviewed_blob = blobInfo["reviewed_blob"]
    logging.info("[CreateReviewedDocumentActivity] Start, blob: %s", reviewed_blob)

    settings = _get_settings()
    service = BlobServiceClient.from_connection_string(settings.azure_web_jobs_storage)

    container_name = "reviewed-clauses"
    in_container = service.get_container_client(container_name)
    reviewed_data = json.loads(in_container.download_blob(reviewed_blob).readall())

    tmp_dir = Path(tempfile.mkdtemp())
    orig_path, rev_path = create_original_and_revised_docs(
        reviewed_data, tmp_dir, reviewed_blob
    )

    out_container = service.get_container_client("reviewed-documents")
    for p in [orig_path, rev_path]:
        blob_name = p.name
        with open(p, "rb") as f:
            out_container.upload_blob(name=blob_name, data=f, overwrite=True)
        logging.info("[CreateReviewedDocumentActivity] Uploaded %s", blob_name)

    shutil.rmtree(tmp_dir)
    return {"original_blob": orig_path.name, "revised_blob": rev_path.name}


@df_app.activity_trigger(input_name="blobInfo")
def DownloadJsonArrayActivity(blobInfo: dict) -> list:
    """Download a JSON blob and parse it into a Python list or dict."""
    settings = _get_settings()
    svc = BlobServiceClient.from_connection_string(settings.azure_web_jobs_storage)
    data = (
        svc.get_container_client(blobInfo["container_name"])
        .download_blob(blobInfo["blob"])
        .readall()
    )
    return json.loads(data)


@df_app.activity_trigger(input_name="blobInfo")
def SaveJsonArrayActivity(blobInfo: dict) -> dict:
    """Save a Python dict/list as a JSON blob."""
    blob_name = f"{blobInfo['base_name']}.reviewed.full.json"
    settings = _get_settings()
    svc = BlobServiceClient.from_connection_string(settings.azure_web_jobs_storage)
    svc.get_container_client(blobInfo["container_name"]).upload_blob(
        name=blob_name,
        data=json.dumps(blobInfo["map"], ensure_ascii=False),
        overwrite=True,
    )
    return {"reviewed_blob": blob_name}


@df_app.activity_trigger(input_name="info")
def SaveUsageActivity(info: dict) -> dict:
    """Serialize usage metrics to a JSON blob in 'usage-metrics' container."""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d-%H-%M")

    settings = _get_settings()
    svc = BlobServiceClient.from_connection_string(settings.azure_web_jobs_storage)
    container = svc.get_container_client("usage-metrics")
    blob_name = f"{info['base_name']}-{timestamp}-log-usage.json"
    container.upload_blob(
        name=blob_name, data=json.dumps(info, ensure_ascii=False), overwrite=True
    )
    return {"blob_name": blob_name}
