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
import tiktoken
import logging

from azure.search.documents.models import VectorizableTextQuery

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
        retrieved_clauses = []
        vector_query = VectorizableTextQuery(
            text=clause["content"],
            k_nearest_neighbors=5,
            fields="text_vector",
        )

        results = list(
            search_client.search(
                search_text=None,
                vector_queries=[vector_query],
                select=["chunk"],
                top=5,
            )
        )

        for result in results:
            retrieved_clauses.append(result["chunk"])

        reference_clauses = "\n\n".join(retrieved_clauses)

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


def review_clauses_with_contract_context(
    clauses, client, index_client, response_format, config
):
    """
    Review clauses for redundancy within the context of a previously indexed contract.

    Retrieves semantically similar clauses from the search index and asks the LLM
    to determine if the revision introduced redundancy. If so, reverts the clause
    and updates the legal problem field.

    Parameters:
        clauses (dict): Mapping of page keys to dicts with 'clauses' lists.
        client (AzureOpenAI): OpenAI client for chat completions.
        index_client (SearchClient): Azure Search client for retrieval and merging.
        response_format: Pydantic model for structured output.
        config (dict): Model configuration.

    Returns:
        dict: {"reviewed_clauses": {...}, "usage": {...}}
    """
    model_config = config
    list_of_reviewed_clauses = {}
    tracker = TokenTracker()

    for page_key, page in clauses.items():
        for clause in page["clauses"]:
            numero_da_clausula = clause["numero_da_clausula"]
            clasula_original = clause["clasula_original"]
            problema_juridico = clause["problema_juridico"]
            clausula_revisada = clause["clausula_revisada"]

            retrieved_clauses = []

            vector_query = VectorizableTextQuery(
                text=clasula_original,
                k_nearest_neighbors=5,
                fields="embedding",
            )

            results = list(
                index_client.search(
                    search_text=None,
                    vector_queries=[vector_query],
                    select=["*"],
                    top=3,
                )
            )

            for result in results:
                retrieved_clauses.append(
                    {
                        "id": result["id"],
                        "numero_da_clausula": result["numero_da_clausula"],
                        "clasula_original": result["clasula_original"],
                        "problema_juridico": result["problema_juridico"],
                        "clausula_revisada": result["clausula_revisada"],
                    }
                )

            prompt = f"""
                Você é um especialista jurídico responsável por validar se a revisão de uma cláusula contratual está redundante ao compará-la com uma outra cláusula que contém o mesmo risco jurídico .

                EXEMPLO 1: REDUNDÂNCIA:

                Cláusula 1
                clausula_original  = "… deve ser devolvida ou destruída pela Receptora ao término do contrato …"
                problema_juridico  = "Não define momento exato da devolução/destruição."
                clausula_revisada  = "… será devolvida ou destruída pela Receptora, desde que identificada previamente …"

                Cláusula 2 (similar)
                clausula_original  = "… serão retornadas ou destruídas pela parte receptora, tão logo solicitado …"
                problema_juridico  = "Já contém obrigação de devolução/destruição."
                clausula_revisada  = "… serão retornadas ou destruídas pela parte receptora ao término do contrato …"

                ✅ Diagnóstico: MESMO risco jurídico → redundância.

                ✅ Ação: manter revisão apenas na cláusula de número MAIOR (2):

                    Cláusula 2 (similar)
                    clausula_original  = "… serão retornadas ou destruídas pela parte receptora, tão logo solicitado …"
                    problema_juridico  = "Já contém obrigação de devolução/destruição."
                    clausula_revisada  = "… serão retornadas ou destruídas pela parte receptora ao término do contrato …"

                    Cláusula 1
                    clausula_original  = "… deve ser devolvida ou destruída pela Receptora ao término do contrato …"
                    problema_juridico  = "Cláusula 1 possui o mesmo risco da Cláusula 2; será tratado na 2."
                    clausula_revisada  = "… deve ser devolvida ou destruída pela Receptora ao término do contrato …"

                EXEMPLO 2 (não-redundante em ciclo):

                Cláusula X (#6.1.4) → já diz:
                problema_juridico = "Cláusula 6.1.4 possui o mesmo risco da 6.1.5; será tratado na 6.1.5."
                Cláusula Y (#6.1.5) (atual)
                *Não revertida* porque X aponta para ela.
                Portanto **NÃO** marcar redundância outra vez.
                Resultado para 6.1.5: campos permanecem como estão.

                ──────────────────────── SUA TAREFA
                Compare a cláusula alvo {numero_da_clausula} com a similar {retrieved_clauses[1]["numero_da_clausula"]} através dos seguintes passos:

                1 - Observe os campos informações da cláusula {numero_da_clausula} e {retrieved_clauses[1]["numero_da_clausula"]}.

                2 - Possuem o mesmo risco jurídico?*
                    Se o número da clásula {numero_da_clausula} é **MENOR** que {retrieved_clauses[1]["numero_da_clausula"]}, devolva {numero_da_clausula} com os 3 campos
                    com alterações conforme especificado no exemplo "1":
                        clausula_original: inalterado
                        problema_juridico: "Cláusula {numero_da_clausula} possui o mesmo risco da Cláusula {retrieved_clauses[1]["numero_da_clausula"]}; será tratado na 2{retrieved_clauses[1]["numero_da_clausula"]}."
                        clausula_revisada: clausula_original
                    Se o número da clásula {numero_da_clausula} é **MAIOR** que {retrieved_clauses[1]["numero_da_clausula"]}, devolva {numero_da_clausula} com os 3 campos sem nenhuma alteração conforme especificado no exemplo "1":
                        clausula_original: inalterado
                        problema_juridico: inalterado
                        clausula_revisada: inalterado

                    Se no campo "problema_juridico" da cláusula {retrieved_clauses[1]["numero_da_clausula"]}, já estiver "Cláusula {numero_da_clausula} possui o mesmo risco da Cláusula {retrieved_clauses[1]["numero_da_clausula"]}; será tratado na
                    {retrieved_clauses[1]["numero_da_clausula"]}, devolva {numero_da_clausula} com os 3 campos sem nenhuma alteração conforme especificado no exemplo "2":
                        clausula_original: inalterado
                        problema_juridico: inalterado
                        clausula_revisada: inalterado

                3 - Se {numero_da_clausula} não possui nenhuma redundância com {retrieved_clauses[1]["numero_da_clausula"]}, devolva {numero_da_clausula} com os campos "clausula_original", "problema_juridico" e "clausula_revisada" completamente inalterados, do jeito que estão.

                REGRAS:

                1 - Você como especialista deve fazer toda uma análise de ambas as clasulas antes de inferir se houve ou não redundância na revisão. A cláusula similar está vindo do banco por similaridade semantica,
                isso não necessariamente siginifica que o risco jurídico é o mesmo.

                2 - Não se esqueça da do exemplo 2 e atente-se ao efeito "circular". Ou seja, se {numero_da_clausula} for redundante e vai ser tratado na {retrieved_clauses[1]["numero_da_clausula"]}, ou vice-versa, quando voce estiver olhando a {retrieved_clauses[1]["numero_da_clausula"]},
            vai estar especiificado que {numero_da_clausula} seria tratado na {retrieved_clauses[1]["numero_da_clausula"]}. Nesse cenário, {retrieved_clauses[1]["numero_da_clausula"]} permancece INALTERADO e não deve apontar de volta para {numero_da_clausula}. Se voce ignorar isso, comprometerá a revisão.

                3 - "Inalterado", significa devolver os campos exatamente como eles vieram.


                📄 **Informações da cláusula {numero_da_clausula}:**
                    clasula_original = {clasula_original}
                    problema_juridico= {problema_juridico}
                    clausula_revisada = {clausula_revisada}

                **Cláusula similar que provavelmente contém o mesmo risco jurídico: **
                    Clásula: {retrieved_clauses[1]["numero_da_clausula"]} \n
                    Clasula Original: {retrieved_clauses[1]["clasula_original"]} \n
                    Problema Juridico: {retrieved_clauses[1]["problema_juridico"]} \n
                    Clausula Revisada: {retrieved_clauses[1]["clausula_revisada"]} \n

            """

            response = client.beta.chat.completions.parse(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um revisor jurídico experiente.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=response_format,
                max_tokens=model_config["max_tokens"],
                temperature=model_config["temperature"],
                top_p=model_config["top_p"],
                model=model_config["deployment"],
            )

            tracker.track(response)

            structured_output = response.choices[0].message.parsed

            list_of_reviewed_clauses[clause["numero_da_clausula"]] = json.loads(
                structured_output.model_dump_json(indent=2)
            )

            index_client.merge_documents(
                documents=[
                    {
                        "id": retrieved_clauses[0]["id"],
                        "clasula_original": list_of_reviewed_clauses[
                            clause["numero_da_clausula"]
                        ]["clauses"][0]["clasula_original"],
                        "problema_juridico": list_of_reviewed_clauses[
                            clause["numero_da_clausula"]
                        ]["clauses"][0]["problema_juridico"],
                        "clausula_revisada": list_of_reviewed_clauses[
                            clause["numero_da_clausula"]
                        ]["clauses"][0]["clausula_revisada"],
                    }
                ]
            )

    return {
        "reviewed_clauses": list_of_reviewed_clauses,
        "usage": tracker.usage,
    }
