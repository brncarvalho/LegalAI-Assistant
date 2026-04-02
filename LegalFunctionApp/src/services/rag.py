import json
import logging

import tiktoken
from openai import AzureOpenAI, OpenAIError

from models.rag import PageOutput, PageReviewedOutput
from src.config.prompts import CLAUSE_EXTRACTION_PROMPT, REVIEW_CLAUSE_PROMPT
from src.config.settings import settings
from src.services.search import SearchService
from src.services.token_tracker import TokenTracker

MAX_EMBEDDING_TOKENS = 8191


class RAGService:
    def __init__(self, search_service: SearchService):
        self.search_service = search_service
        self.tracker_service = TokenTracker()
        self.client = AzureOpenAI(
            api_version=settings.api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
        )

    def _run_queries(self, query: str, limit: int = 5) -> str:
        all_results = []
        search_results = self.search_service.search(query, limit)
        all_results.extend([result.text for result in search_results.results])
        return "\n\n".join(all_results)

    def _generate_completion(self, prompt: str, response_format=None):

        try:
            return self.client.beta.chat.completions.parse(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format=response_format,
            )
        except OpenAIError as e:
            logging.error("LLM completion failed: %s", e)
            raise

    def _extract_clause(self, chunks: list[dict]) -> dict:

        filtered_clauses = {}

        i = 0
        for chunk in chunks:
            prompt = CLAUSE_EXTRACTION_PROMPT.format(chunks=chunk["content"])
            response = self._generate_completion(prompt, PageOutput)

            extract_tracker = self.tracker_service.track(response)

            structured_output = response.choices[0].message.parsed
            filtered_clauses[i] = json.loads(structured_output.model_dump_json(indent=2))
            i += 1

        return {
            "clauses": filtered_clauses,
            "usage": extract_tracker.usage,
        }

    def _review_clause(self, clauses: list, termo: str) -> dict:

        encoding = tiktoken.get_encoding("cl100k_base")
        list_of_reviewed_clauses = {}

        for clause in clauses:
            clause_content = clause["content"]
            clause_number = clause["clause_number"]

            if not clause_content or not clause_number:
                logging.warning("Empty clause found: %s. Skipping.", clause.get("clause_number"))
                continue

            clause_content = clause_content.strip()
            clause_number = clause_number.strip()

            tokens = encoding.encode(clause_content)
            if len(tokens) > MAX_EMBEDDING_TOKENS:
                logging.warning("Clause exceeded token limit (%d tokens). Skipping.", len(tokens))
                continue

            context = self._run_queries(clause)
            prompt = REVIEW_CLAUSE_PROMPT.format(
                termo=termo, clause=clause, reference_clauses=context
            )
            response = self._generate_completion(prompt, PageReviewedOutput)

            review_tracker = self.tracker_service.track(response)

            structured_output = response.choices[0].message.parsed

            list_of_reviewed_clauses[clause["clause_number"]] = json.loads(
                structured_output.model_dump_json(indent=2)
            )

        return {
            "reviewed_clauses": list_of_reviewed_clauses,
            "usage": review_tracker.usage,
        }
