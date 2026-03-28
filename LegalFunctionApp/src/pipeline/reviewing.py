"""
Core legal clause review logic.

This module handles the LLM-powered legal review of contract clauses:
- review_clauses: Primary review using reference clauses from Azure Search
- review_clauses_with_contract_context: Redundancy detection across clauses

Other responsibilities have been split into focused modules:
- filtering.py: Clause extraction from raw text
- document_generation.py: Word document creation
- deduplication.py: Merging overlapping clauses
- search.py: Search index management
- utils/retry.py: LLM retry logic
"""

import json
import logging

import tiktoken
from services.search import SearchService
from config.settings import settings

from src.utils.retry import safe_parse_with_retry
from src.utils.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


def review_clauses(clauses, client, search_client, response_format, config, termo):
    """
    Review and legally validate contract clauses using Azure Cognitive Search
    for reference retrieval and Azure OpenAI for structured legal review.

    Parameters:
        clauses (list[dict]): Each dict must have 'content' and 'clause_number' keys.
        client (AzureOpenAI): Initialized OpenAI client for chat completions.
        search_client (SearchClient): Azure Search client for reference clause retrieval.
        response_format: Pydantic model for structured output parsing.
        config (dict): Model configuration (max_tokens, temperature, top_p, deployment).
        termo (str): Party role — "contratante" or "contratada".

    Returns:
        dict: {"reviewed_clauses": {clause_number: review_result, ...}, "usage": {...}}
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    list_of_reviewed_clauses = {}
    tracker = TokenTracker()

    for clause in clauses:
        clause_content = clause["content"]
        clause_number = clause["clause_number"]

        if not clause_content or not clause_number:
            logger.warning("Empty clause found: %s. Skipping.", clause.get("clause_number"))
            continue

        clause_content = clause_content.strip()
        clause_number = clause_number.strip()

        tokens = encoding.encode(clause_content)
        if len(tokens) > 8191:
            logger.warning("Clause exceeded token limit (%d tokens). Skipping.", len(tokens))
            continue

        # Retrieve similar reference clauses from Azure Search
        search_service = SearchService(
            ai_search_url=settings.azure_ai_search_endpoint,
            index_name=settings.index_name,
            ai_search_api_key=settings.azure_ai_search_api_key,
        )

        retrieved_clauses = search_service.search(query=clause_content, limit=5)

        reference_clauses = "\n\n".join(result.content for result in retrieved_clauses)

        prompt = f"""
        Você é um **advogado sênior** responsável por revisar cláusulas contratuais, utilizando exclusivamente um conjunto de **cláusulas de referência** previamente aprovadas e assinadas pelo Departamento Jurídico da empresa.

        Embora você deva sempre fazer a análise mais correta e justa, você pode se enviesar levemente caso a Logicalis seja a **contratante** e se posicionar como tal para garantir a máxima proteção jurídica para a empresa, porém caso a Logicalis seja a **contratada**
        você deve buscar o mínimo de responsabilidade para a empresa, garantindo assim a convergência entre o rigor da sua análise e os interesses da empresa.
        ---

        ## Instruções

        1. **Base normativa**
        - Utilize apenas o conteúdo jurídico contido nas cláusulas de referência.
        - Não introduza disposições que não constem em pelo menos uma referência.
        - Quando as referências divergir em grau de proteção, adote a solução mais restritiva, desde que nenhuma referência a contrarie.

        2. **Critérios de avaliação**
        - **Alinhada** A cláusula alvo reproduz o conteúdo jurídico essencial das referências. → Mantenha‑a sem alterações.
        - **Parcialmente alinhada** Existe lacuna pontual (ex.: ausência de exceção legal, de limite de responsabilidade, de prazo). → Inserir apenas o ponto faltante.
        - **Desalinhada** A cláusula conflita com o padrão (ex.: amplia responsabilidade; omite obrigação mandatória). → Ajustar minimamente para restabelecer a conformidade.

        3. **Regras e princípios de redação**

        3.1 **Mudança mínima** Preservar numeração, termos definidos, capitalização, estrutura (listas, alíneas) e tom do contrato do cliente. Alterar somente o indispensável.
        3.2 **Placeholders** Marcas de anonimização entre colchetes nas referências (ex.: `[PRAZO]`, `[NOME]`) **não são requisitos**. Ignore‑as como variáveis. Não insira esses placeholders na cláusula revisada, são somente máscaras de anonimização do banco, o foco é sempre o contéudo jurídico.
        3.3 **Cláusulas que citam anexos ou documentos externos** :
            ‑ **Não** incorporar listas de anexos, números, versões ou descrições que venham apenas das referências.
            ‑ Se faltar detalhamento ou enumeração de anexos, registre o fato em `problema_juridico`, mas **mantenha a cláusula original** — as Partes precisam revisar manualmente, pois o você não tem acesso aos anexos.
            ‑ Só altere se houver conflito jurídico expresso (por exemplo, cláusula original concede prioridade ao anexo em detrimento do contrato, mas as referências impõem o inverso).

             Exemplo de saída desejada:

             Clausula orignal:

             X. Constituem parte integrante e indissociável do presente Contrato os seus Anexos, conforme indicado na Lista de Anexos do Termo de Contratação ("Anexos").

             Clasula revisada:

             X. Constituem parte integrante e indissociável do presente Contrato os seus Anexos, conforme indicado na Lista de Anexos do Termo de Contratação ("Anexos").

             problema_juridico: A cláusula original não especifica os anexos que integram o contrato, nem estabelece regras para resolução de conflitos entre disposições do contrato e dos anexos, o que pode gerar ambiguidades. Como não tenho detalhamento dos
             anexos, mantive a cláusula sem alteração porém com as pontuações anteriores.


        3.4 **Sem correção gramatical** (a menos que a alteração jurídica exija).
        3.5 **Sem comparações literais**; descreva o risco jurídico de forma objetiva.

        **Exemplo de Revisão**:

            Clausula original:

            X. Propriedade. Toda a informação Confidencial, a não ser que de outro modo tenha sido estabelecido por escrito entre
            as Partes, permanecerá sendo de propriedade da Parte que transmitir a Informação Confidencial, somente podendo ser
            usada pela parte receptora para os fins deste Acordo de Confidencialidade. Tais Informações Confidenciais, incluídas as
            cópias realizadas, em prazo razoável serão retornadas para a parte que as transmitiu, ou então destruídas pela parte receptora, tão logo solicitado pela parte transmissora e, em
            qualquer caso, na hipótese de término deste Acordo de Confidencialidade. A pedido da parte que transmitir a Informação Confidencial, a parte receptora deverá prontamente
            emitir uma declaração a ser assinada por seu representante legal, confirmando que toda a Informação Confidencial não retornada para a parte transmissora foi inteiramente destruída.

            Cláusula revisada:

             5 - Toda a informação Confidencial, a não ser que de outro modo tenha sido estabelecido por escrito entre as Partes, permanecerá sendo de propriedade da Parte que transmitir a Informação Confidencial, somente podendo ser usada pela parte receptora para os fins deste Acordo de Confidencialidade. Tais Informações Confidenciais, incluídas as cópias realizadas, em prazo razoável serão retornadas para a parte que as transmitiu,
             ou então destruídas pela parte receptora, tão logo solicitado pela parte transmissora, exceto aquelas que sejam exigidas por lei ou regulamento para retenção pela parte receptora, ou que estejam armazenadas automaticamente em sistemas de backup acessíveis apenas em situações excepcionais e não no curso normal dos negócios. A pedido da parte que transmitir a Informação Confidencial, a parte receptora deverá prontamente emitir uma declaração a ser assinada por seu representante legal,
             confirmando que toda a Informação Confidencial não retornada para a parte transmissora foi inteiramente destruída, ou que está armazenada exclusivamente conforme exceções legais ou técnicas acima mencionadas.

             Justificativa da alteração (problema_jurídico): "A cláusula não aborda a possibilidade de retenção de informações confidenciais por motivos legais, nem detalha exceções ou limitações à destruição ou devolução de informações confidenciais, o que pode gerar conflitos com obrigações legais ou regulatórias."


        4. **Saída obrigatória (JSON)**
        Devolva exatamente no formato abaixo:

        ```json
        [
            "numero_da_clausula": "<identificador original>",
            "clasula_original": "<texto original>",
            "problema_juridico": "<descrição objetiva ou 'Cláusula alinhada juridicamente às referências.'>",
            "clausula_revisada": "<texto após ajustes (ou original, se nenhum ajuste)>"
        ]


        A cláusula a seguir a ser revisada, a Logicalis está atuando como **{termo}**:

        📄 **Cláusula:**
        {clause["clause_number"] + clause["content"]}

        **Cláusulas de Referência (juridicamente aprovadas):**
        {reference_clauses}
        """

        messages = [
            {"role": "system", "content": "Você é um revisor jurídico experiente."},
            {"role": "user", "content": prompt},
        ]

        response = safe_parse_with_retry(client, messages, response_format, config)
        tracker.track(response)

        structured_output = response.choices[0].message.parsed

        list_of_reviewed_clauses[clause["clause_number"]] = json.loads(
            structured_output.model_dump_json(indent=2)
        )

    return {
        "reviewed_clauses": list_of_reviewed_clauses,
        "usage": tracker.usage,
    }
