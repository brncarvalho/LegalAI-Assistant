import win32com.client as win32
from pathlib import Path
import tempfile
import shutil
from rapidfuzz import process, fuzz
import os
import json
import pythoncom
from azure.storage.blob import BlobServiceClient


def redline_contract(reviewed_data: dict, original_doc: Path, out_doc: Path):
    wd = win32.gencache.EnsureDispatch("Word.Application")
    wd.Visible = False

    tmp_clone = Path(tempfile.mkdtemp()) / "working_copy.docx"
    shutil.copy2(original_doc, tmp_clone)

    doc = wd.Documents.Open(str(tmp_clone))
    doc.TrackRevisions = False

    candidate_map = get_all_paragraphs_robust(doc)

    search_corpus = {
        k: v.Range.Text.strip()
        for k, v in candidate_map.items()
        if len(v.Range.Text.strip()) > 10
    }

    print(f"--- Indexed {len(search_corpus)} text blocks from doc ---")

    clauses_to_process = [c for pg in reviewed_data.values() for c in pg["clauses"]]
    taken_ids = set()

    for cl in clauses_to_process:
        original_llm_txt = cl["clasula_original"]
        revised_txt = cl["clausula_revisada"]

        if not original_llm_txt or len(original_llm_txt) < 10:
            continue

        match = process.extractOne(
            original_llm_txt,
            search_corpus,
            scorer=fuzz.ratio,
            score_cutoff=65,
        )

        if not match:
            print(f"[MISS] Could not find match for: {cl.get('numero_da_clausula')}")
            continue

        best_text, score, unique_id = match

        if unique_id in taken_ids:
            print(f"[SKIP] ID {unique_id} already modified.")
            continue

        target_para = candidate_map[unique_id]

        len_diff_ratio = len(revised_txt) / len(best_text)
        if len_diff_ratio < 0.3:
            print(
                f"[DANGER] Skipping {unique_id}: Replacement text is too short compared to original (Possible Blob)."
            )
            continue

        print(
            f"[HIT] {score:.1f}% Match found for {cl.get('numero_da_clausula')} - Replacing..."
        )

        rng = target_para.Range

        rng.MoveEnd(Unit=win32.constants.wdCharacter, Count=-1)
        rng.Text = revised_txt

        if cl.get("problema_juridico"):
            doc.Comments.Add(rng, cl["problema_juridico"])

        taken_ids.add(unique_id)

    doc.Save()
    doc.Close()

    print("--- Generating Redline ---")
    orig_ref = wd.Documents.Open(str(original_doc), ReadOnly=True)
    revised_ref = wd.Documents.Open(str(tmp_clone), ReadOnly=True)

    diff = wd.CompareDocuments(
        OriginalDocument=orig_ref,
        RevisedDocument=revised_ref,
        Destination=win32.constants.wdCompareTargetNew,
        Granularity=win32.constants.wdGranularityWordLevel,
        CompareWhitespace=False,
        CompareFormatting=False,
        RevisedAuthor="AI Reviewer",
    )

    diff.SaveAs2(str(out_doc), FileFormat=16)
    diff.Close(False)
    orig_ref.Close(False)
    revised_ref.Close(False)
    wd.Quit()
    print(f"✓ Process Complete. Saved to: {out_doc}")


def get_all_paragraphs_robust(doc):
    """
    Crawls the MAIN BODY, ALL TABLES, and ALL SHAPES (Text Boxes).
    Returns a dict: { unique_id : ParagraphObject }
    """
    candidates = {}
    counter = 0

    for p in doc.Paragraphs:
        candidates[counter] = p
        counter += 1

    for shape in doc.Shapes:
        if shape.TextFrame.HasText:
            for p in shape.TextFrame.TextRange.Paragraphs:
                candidates[counter] = p
                counter += 1

    for table in doc.Tables:
        for row in table.Rows:
            for cell in row.Cells:
                for p in cell.Range.Paragraphs:
                    candidates[counter] = p
                    counter += 1

    return candidates


class AzureWordProcessor:
    def __init__(self, connection_string):
        self.blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )

    def download_to_temp(self, container_name, blob_name, suffix=".docx"):
        """Downloads a blob to a local temp file and returns the Path object."""

        tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = Path(tf.name)
        tf.close()

        print(f"⬇️ Downloading {blob_name} to {temp_path}...")

        blob_client = self.blob_service_client.get_blob_client(
            container=container_name, blob=blob_name
        )

        with open(temp_path, "wb") as file:
            download_stream = blob_client.download_blob()
            file.write(download_stream.readall())

        return temp_path

    def upload_from_temp(self, local_path, container_name, blob_name):
        """Uploads a local file to Azure Blob."""
        print(f"⬆️ Uploading result to {container_name}/{blob_name}...")

        blob_client = self.blob_service_client.get_blob_client(
            container=container_name, blob=blob_name
        )

        with open(local_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

    def get_json_data(self, container_name, blob_name):
        """Downloads and parses a JSON blob directly into a Python dict."""
        blob_client = self.blob_service_client.get_blob_client(
            container=container_name, blob=blob_name
        )
        json_stream = blob_client.download_blob().readall()
        return json.loads(json_stream)


def run_redline_pipeline(
    conn_string: str,
    json_container: str,
    json_blob: str,
    doc_container: str,
    doc_blob: str,
    output_container: str,
    output_blob_name: str,
):
    processor = AzureWordProcessor(conn_string)

    print("--- Fetching Review Data ---")
    reviewed_data = processor.get_json_data(json_container, json_blob)

    original_temp_path = processor.download_to_temp(
        doc_container, doc_blob, suffix=".docx"
    )

    out_temp_path = Path(tempfile.gettempdir()) / f"redline_{os.urandom(4).hex()}.docx"

    try:
        pythoncom.CoInitialize()

        print("--- Starting Redline Process ---")

        redline_contract(
            reviewed_data=reviewed_data,
            original_doc=original_temp_path.resolve(),
            out_doc=out_temp_path.resolve(),
        )

        processor.upload_from_temp(out_temp_path, output_container, output_blob_name)
        print("Pipeline Success!")

    except Exception as e:
        print(f"Error: {e}")
        raise e

    finally:
        if original_temp_path.exists():
            os.remove(original_temp_path)
        if out_temp_path.exists():
            os.remove(out_temp_path)

        pythoncom.CoUninitialize()
