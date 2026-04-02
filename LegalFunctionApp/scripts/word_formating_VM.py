import json
import os
import shutil
import tempfile
from pathlib import Path

import pythoncom
import win32com.client as win32
from azure.storage.blob import BlobServiceClient
from rapidfuzz import fuzz, process


def redline_contract(reviewed_data: dict, original_doc: Path, out_doc: Path):
    wd = win32.gencache.EnsureDispatch("Word.Application")
    wd.Visible = False

    tmp_clone = Path(tempfile.mkdtemp()) / "working_copy.docx"
    shutil.copy2(original_doc, tmp_clone)

    doc = wd.Documents.Open(str(tmp_clone))
    doc.TrackRevisions = False

    candidate_map = get_all_paragraphs(doc)

    search_corpus = {
        k: v.Range.Text.strip() for k, v in candidate_map.items() if len(v.Range.Text.strip()) > 10
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

        print(f"[HIT] {score:.1f}% Match found for {cl.get('numero_da_clausula')} - Replacing...")

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


def get_all_paragraphs(doc):
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
