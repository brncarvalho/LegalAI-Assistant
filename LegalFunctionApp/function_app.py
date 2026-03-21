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
from src.llm.clients import (
    get_openai_client,
    get_model_config,
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
    Triggered when a new PDF is uploaded to the 'contracts-container' blob storage.
    Starts the durable orchestration with the blob filename as input.

    Parameters:
        blob: The uploaded blob stream (InputStream).
        starter: DurableOrchestrationClient used to launch the orchestrator.
    """

    # Extract just the filename from the blob path
    filename = blob.name.split("/")[-1]
    logging.info(f"[blob_start] New PDF arrived: {filename}")

    # Start a new orchestration instance called "Orchestrator"
    instance_id = await starter.start_new(
        "Orchestrator", client_input={"blob_name": filename}
    )
    logging.info(f"[blob_start] Orchestration started: {instance_id}")


@df_app.orchestration_trigger(context_name="context")
def Orchestrator(context: df.DurableOrchestrationContext):
    """
    Durable Functions orchestrator that coordinates the full contract review workflow.

    Steps:
      1. Extract raw JSON from the PDF and save.
      2. Filter clauses from the JSON.
      3. Download filtered clauses as an array.
      4. Split into chunks and review each chunk in parallel.
      5. Merge partial review results and save intermediate blob.
      6. Create a temporary search index and upload reviewed clauses.
      7. Split for double-check review, run in parallel, and merge.
      8. Save final reviewed clauses and generate the reviewed document.
      9. Record usage statistics and save to a blob.

    Parameters:
        context: DurableOrchestrationContext providing input and task orchestration.

    Returns:
        dict: Contains final document info and the blob name where usage stats are stored.
    """

    # Retrieve the input payload (blob_name)
    payload = context.get_input()
    logging.info(f"[Orchestrator] Received payload: {payload}")

    blob_name = payload["blob_name"]
    stem = Path(blob_name).stem
    maybe_party = stem.rsplit("-", 1)[-1].lower() if "-" in stem else None
    party = maybe_party if maybe_party in {"contratante", "contratada"} else None
    logging.info(f"[Orchestrator] Detected party: {party}")

    # 1. Extract raw JSON from PDF
    raw_info = yield context.call_activity("ExtractAndSaveActivity", payload)
    logging.info(f"[Orchestrator] Raw JSON written to blob: {raw_info['raw_blob']}")

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
        f"[Orchestrator] Recebeu partial_results: {[len(r) for r in partial_results]}"
    )

    total_usage = {
        "prompt": 0,
        "completion": 0,
        "total": 0,
    }

    # Merge all partial review outputs and accumulate usage
    extracted_merged: list[dict] = []
    for part in partial_results:
        extracted_merged.extend(part["filtered_blob"])
        total_usage["prompt"] += part["usage"]["prompt"]
        total_usage["completion"] += part["usage"]["completion"]
        total_usage["total"] += part["usage"]["total"]

    logging.info(f"[Orchestrator] Merged total: {len(extracted_merged)} clauses")

    # 5. Save merged review to a blob for intermediate storage
    extracted_merged_blob_info = yield context.call_activity(
        "SaveJsonArrayActivity",
        {
            "map": extracted_merged,
            "base_name": Path(extracted_blob).stem,
            "container_name": "extracted-clauses",
        },
    )
    logging.info(
        f"[Orchestrator] SaveJsonArrayActivity gravou: {extracted_merged_blob_info['reviewed_blob']}"
    )

    # ---------------------------------------------------------------------------------------------------------------

    # 3. Download the filtered clauses as an array
    filtered_blob = extracted_merged_blob_info["reviewed_blob"]
    clauses_array = yield context.call_activity(
        "DownloadJsonArrayActivity",
        {"blob": filtered_blob, "container_name": "extracted-clauses"},
    )

    logging.info(
        f"[Orchestrator] DownloadJsonArrayActivity returned {len(clauses_array)} clauses"
    )

    # Split clauses into fixed-size chunks for parallel review
    chunk_size = 5
    chunks = [
        clauses_array[i : i + chunk_size]
        for i in range(0, len(clauses_array), chunk_size)
    ]

    logging.info(f"[Orchestrator] Dividiu em {len(chunks)} chunks de até {chunk_size}")

    # 4. Kick off parallel review tasks
    tasks = [
        context.call_activity(
            "ReviewClausesChunkActivity", {"chunk": chunk, "party": party}
        )
        for chunk in chunks
    ]
    logging.info(
        f"[Orchestrator] Disparando {len(tasks)} ReviewClausesChunkActivity em paralelo"
    )

    partial_results = yield context.task_all(tasks)

    logging.info(
        f"[Orchestrator] Recebeu partial_results: {[len(r) for r in partial_results]}"
    )

    # Merge all partial review outputs and accumulate usage
    merged: dict[str, dict] = {}
    for part in partial_results:
        merged.update(part["reviewed_clauses"])
        total_usage["prompt"] += part["usage"]["prompt"]
        total_usage["completion"] += part["usage"]["completion"]
        total_usage["total"] += part["usage"]["total"]

    logging.info(f"[Orchestrator] Merged total: {len(merged)} clauses")

    # 5. Save merged review to a blob for intermediate storage
    merged_blob_info = yield context.call_activity(
        "SaveJsonArrayActivity",
        {
            "map": merged,
            "base_name": Path(filtered_blob).stem,
            "container_name": "reviewed-clauses",
        },
    )
    logging.info(
        f"[Orchestrator] SaveJsonArrayActivity gravou: {merged_blob_info['reviewed_blob']}"
    )

    # 10. Generate the final reviewed document
    final_doc = yield context.call_activity(
        "CreateReviewedDocumentActivity", merged_blob_info
    )

    # Build usage metadata and save it
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

    # Return final document info plus the usage stats blob name
    return {**final_doc, "usage_blob": usage_blob["blob_name"]}


# --- 2) Activities ---


@df_app.activity_trigger(input_name="payload")
def ExtractAndSaveActivity(payload: dict) -> list:
    """
    Download a PDF from blob storage, extract text as JSON chunks, apply token overlap,
    and save the raw JSON back to blob storage.

    Parameters:
        payload (dict): Contains 'blob_name' key with the PDF filename.

    Returns:
        dict: {'raw_blob': <name of JSON blob>} indicating where the raw chunks were saved.
    """

    blob_name = payload["blob_name"]
    logging.info(f"[ExtractAndSaveActivity] Start extracting `{blob_name}`")

    # Connect to Azure Blob Storage using the storage connection string
    storage = BlobServiceClient.from_connection_string(os.getenv("AzureWebJobsStorage"))
    container = storage.get_container_client("contracts-container")

    # Download the PDF to a temporary file
    downloader = container.download_blob(blob_name)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(downloader.readall())
        tmp.flush()
        pdf_path = tmp.name

    # Use the document intelligence pipeline to get JSON, chunk by page, and overlap tokens
    contract_json = extract_contract_json(pdf_path, "layout")
    chunks = apply_page_overlap(contract_json, overlap_pages=2)

    logging.info(
        f"[ExtractAndSaveActivity] Extracted and overlapped {len(chunks)} chunks"
    )

    # Prepare JSON filename and upload to the 'output' container
    raw_blob = blob_name.rsplit(".", 1)[0] + ".json"
    raw_container = storage.get_container_client("output")
    raw_container.upload_blob(
        name=raw_blob, data=json.dumps(chunks, ensure_ascii=False), overwrite=True
    )
    logging.info(f"[ExtractAndSaveActivity] Raw JSON saved as `{raw_blob}`")

    return {"raw_blob": raw_blob}


@df_app.activity_trigger(input_name="blobInfo")
def FilterClausesActivity(blobInfo: list) -> list:
    """
    Load raw JSON chunks from blob, filter and extract clauses via GPT-4o,
    merge overlapping clauses, and save filtered output back to blob.

    Parameters:
        blobInfo (dict): {'raw_blob': <name of JSON blob>}

    Returns:
        dict:
          - 'filtered_blob': filename of saved filtered JSON
          - 'usage': token usage metrics from the filtering step
    """

    chunks = blobInfo

    # Initialize OpenAI client and model config
    client = get_openai_client("gpt_4o")
    model_cfg = get_model_config()["openai_models"]["gpt_4o"]

    # Call the clause-filtering pipeline
    filtered = filter_clauses_with_gpt4o(chunks, client, PageOutput, model_cfg)
    clean_clauses = deduplicate_clauses(filtered)

    usage = filtered["usage"]
    logging.info(f"[FilterClausesActivity] Filtered down to {len(filtered)} clauses")

    return {"filtered_blob": clean_clauses, "usage": usage}


@df_app.activity_trigger(input_name="clauseschunk")
def ReviewClausesChunkActivity(clauseschunk: dict) -> dict:
    """
    Review a chunk of clauses via GPT-4o, normalize numbering, assign UUIDs,
    and return structured review results and usage metrics.

    Parameters:
        clauseschunk (list): List of clause dicts to review.

    Returns:
        dict:
          - 'reviewed_clauses': merged and normalized clauses with UUIDs
          - 'usage': token usage metrics from the review step
    """

    if isinstance(clauseschunk, dict):
        chunk = clauseschunk.get("chunk", [])
        party = clauseschunk.get("party")
    else:
        # backward-compat if ever called with a raw list
        chunk = clauseschunk
        party = None

    # Initialize OpenAI client and model config
    client = get_openai_client("gpt_4o")
    model_cfg = get_model_config()["openai_models"]["gpt_4o"]

    # Run the legal review pipeline
    reviewed_clauses = review_clauses(
        chunk, client, PageReviewedOutput, model_cfg, party
    )

    # Normalize clause numbering and assign unique IDs
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
    Download reviewed clauses JSON, create original & revised Word docs with compare/comments,
    upload both documents to blob storage, and return their blob names.

    Parameters:
        blobInfo (dict): {'reviewed_blob': <name of reviewed JSON blob>}

    Returns:
        dict: {
            'original_blob': filename of original-text .docx,
            'revised_blob': filename of revised-text .docx
        }
    """
    reviewed_blob = blobInfo["reviewed_blob"]

    logging.info(f"[CreateReviewedDocumentActivity] >>> start, blobInfo: {blobInfo!r}")

    conn_str = os.getenv("AzureWebJobsStorage")
    service = BlobServiceClient.from_connection_string(conn_str)

    # Download the reviewed JSON from storage

    reviewed_blob = blobInfo["reviewed_blob"]
    container_name = "reviewed-clauses"
    blob_name = reviewed_blob
    in_container = service.get_container_client(container_name)
    reviewed_data = json.loads(in_container.download_blob(blob_name).readall())

    # Generate the Word documents locally
    tmp_dir = Path(tempfile.mkdtemp())
    orig_path, rev_path = create_original_and_revised_docs(
        reviewed_data, tmp_dir, reviewed_blob
    )

    # Upload both docs to 'reviewed-documents' container
    out_container = service.get_container_client("reviewed-documents")
    for p in [orig_path, rev_path]:
        blob_name = p.name
        with open(p, "rb") as f:
            out_container.upload_blob(name=blob_name, data=f, overwrite=True)
        logging.info(f"[CreateReviewedDocumentActivity] uploaded {blob_name}")

    shutil.rmtree(tmp_dir)
    return {"original_blob": orig_path.name, "revised_blob": rev_path.name}


@df_app.activity_trigger(input_name="blobInfo")
def DownloadJsonArrayActivity(blobInfo: dict) -> list:
    """
    Download a JSON blob and parse it into a Python list or dict.

    Parameters:
        blobInfo (dict): {'blob': <blob name>, 'container_name': <container>}

    Returns:
        list or dict: Parsed JSON content.
    """

    svc = BlobServiceClient.from_connection_string(os.getenv("AzureWebJobsStorage"))
    data = (
        svc.get_container_client(blobInfo["container_name"])
        .download_blob(blobInfo["blob"])
        .readall()
    )
    return json.loads(data)


@df_app.activity_trigger(input_name="blobInfo")
def SaveJsonArrayActivity(blobInfo: dict) -> dict:
    """
    Save a Python dict/list as a JSON blob with a '.reviewed.full.json' suffix.

    Parameters:
        blobInfo (dict): {
          'map': data to save,
          'base_name': base filename,
          'container_name': target container
        }

    Returns:
        dict: {'reviewed_blob': <name of saved JSON blob>}

    """

    blob_name = f"{blobInfo['base_name']}.reviewed.full.json"
    svc = BlobServiceClient.from_connection_string(os.getenv("AzureWebJobsStorage"))
    svc.get_container_client(blobInfo["container_name"]).upload_blob(
        name=blob_name,
        data=json.dumps(blobInfo["map"], ensure_ascii=False),
        overwrite=True,
    )
    return {"reviewed_blob": blob_name}


@df_app.activity_trigger(input_name="info")
def SaveUsageActivity(info: dict) -> dict:
    """
    Serialize usage metrics to a JSON blob in 'usage-metrics' container, timestamped.

    Parameters:
        info (dict): Usage data including prompt, completion, total tokens, and metadata.

    Returns:
        dict: {'blob_name': <name of the usage JSON blob>}
    """

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d-%H-%M")

    conn_str = os.getenv("AzureWebJobsStorage")
    svc = BlobServiceClient.from_connection_string(conn_str)
    container = svc.get_container_client("usage-metrics")
    blob_name = f"{info['base_name']}-{timestamp}-log-usage.json"
    container.upload_blob(
        name=blob_name, data=json.dumps(info, ensure_ascii=False), overwrite=True
    )
    return {"blob_name": blob_name}
