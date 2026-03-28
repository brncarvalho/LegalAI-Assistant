from openai import AzureOpenAI
from config.settings import settings
from models.rag import RAGResponse
from services.search import SearchService
from config.prompts import RAG_PROMPT
import instructor


class RAGService:
    def __init__(self, search_service: SearchService):
        self.search_service = search_service
        self.client = AzureOpenAI(
            api_version=settings.api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
        )

    def generate_completion(self, query: str, limit: int = 5):
        search_results = self.search_service.search(query, limit)

        context = "\n\n".join(result.text for result in search_results.results)

        prompt = RAG_PROMPT.format(context=context, query=query)

        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        return RAGResponse(query=query, answer=response.choices[0].message.content)


a = instructor.from_groq
