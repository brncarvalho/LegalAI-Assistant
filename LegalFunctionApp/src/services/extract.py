"""
Contract document extraction and clause processing.

Handles PDF extraction via Azure Document Intelligence and
clause chunking/overlap/normalization logic.
"""

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentContentFormat
from azure.core.credentials import AzureKeyCredential


class ExtractionService:
    def __init__(
        self, azure_ai_doc_intelligence_endpoint: str, azure_ai_doc_intelligence_api_key: str
    ):
        self.azure_ai_doc = DocumentIntelligenceClient(
            endpoint=azure_ai_doc_intelligence_endpoint,
            credential=AzureKeyCredential(azure_ai_doc_intelligence_api_key),
        )

    def extract_contract_json(self, filepath, type="contract"):
        """
        Extract text from a contract PDF using Azure Document Intelligence.

        Parameters:
            doc_client: An initialized DocumentIntelligenceClient.
            filepath (str): Path to the PDF file.
            type (str): 'contract' for prebuilt-contract model, 'layout' for prebuilt-layout.

        Returns:
            dict or list: Full analysis dict (contract mode) or list of page content strings (layout mode).
        """
        if type == "contract":
            with open(filepath, "rb") as f:
                poller = self.azure_ai_doc.begin_analyze_document(
                    model_id="prebuilt-contract",
                    body=f,
                    output_content_format=DocumentContentFormat.TEXT,
                )
                result = poller.result()
                return result.as_dict()

        elif type == "layout":
            with open(filepath, "rb") as f:
                poller = self.azure_ai_doc.begin_analyze_document(
                    model_id="prebuilt-layout",
                    body=f,
                    output_content_format=DocumentContentFormat.MARKDOWN,
                )
                result = poller.result()

                chunks = []
                for page in result.pages:
                    content = result.content[
                        page.spans[0]["offset"] : page.spans[0]["offset"] + page.spans[0]["length"]
                    ]
                    chunks.append(content)

                return chunks
