"""
Clause extraction and filtering using GPT-4o.

Sends raw contract page chunks to an LLM with detailed extraction prompts
to identify numbered clauses, group sub-items, and produce structured output.
"""

import json

from src.utils.retry import safe_parse_with_retry


def filter_clauses_with_gpt4o(chunks, client, response_format, config):
    """
    Extract and filter contract clauses from text chunks using GPT-4o.

    Sends each page chunk to GPT-4o with a detailed prompt instructing it to
    identify clause structures (e.g. "3.", "3.5.", "a.", "i."), ignore headers,
    preserve numbering, and group sub-items under their parent clause.

    Parameters:
        chunks (list[dict]): Each dict must contain a 'content' key.
        client (AzureOpenAI): Initialized GPT-4o client for chat completions.
        response_format: Pydantic model for structured output parsing.
        config (dict): Model parameters (max_tokens, temperature, top_p, deployment).

    Returns:
        dict: {
            "clauses": {page_index: PageOutput dict, ...},
            "usage": {"prompt": int, "completion": int, "total": int}
        }
    """
    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    filtered_clauses = {}

    i = 0
    for chunk in chunks:
        prompt = """

            Você é um doutor especializado em análise de documentos jurídicos empresariais.

            ## Objetivo
            Extrair **somente cláusulas numeradas** (por exemplo, `3.`, `3.5.`, `4.1.2.`) e **agrupar dentro do conteúdo da cláusula** todos os seus **subitens** (por exemplo, `a)`, `b)`, `i)`, `ii)`).
            **Não** separar subitens em itens independentes: eles devem aparecer **dentro do `content` da cláusula-pai**.

            ## Instruções de extração

            1. **Identificação de marcadores principais**
            - Um marcador principal é qualquer numeração no formato decimal pontuado: `N.`, `N.N.`, `N.N.N.` (o ponto final pode ou não aparecer no texto original).
                Exemplos válidos: `11.`, `12`, `28.2`, `4.1.2.`
            - Se o número vier por extenso ou em algarismos romanos (ex.: **"Cláusula Décima Quarta"**, **"XII"**), **converta** para a forma decimal pontuada:
                - "Cláusula Décima Quarta" → `14.`
                - "XII" → `12.`

                **Exemplo (entrada):**
                    11.1. A CONTRATADA deverá manter os registros...
                    12. A Vigência do contrato se manterá...
                    ...
                    XII – As penalidades serão aplicadas..
                **Exemplo (saída):**
                ```json
                    [
                    "clause_number": "11.1", "content": "A CONTRATADA deverá manter os registros..." ,
                    "clause_number": "12", "content": "As penalidades serão aplicadas",
                    "clause_number": "14", "content": "Vigência"
                    ]

            1A. **Proibição de sintetizar cláusula-pai**

               - Nunca crie um número de cláusula pai que não apareça explicitamente no texto disponível (página atual + até 3 seguintes).

               - Se existirem 2.1, 2.2, 2.3, mas não existir 2 visível, não produza a cláusula 2. Extraia cada 2.X separadamente.

               **Exemplo (entrada):**
                   "2.1. Constituem parte integrante...
                    2.2. Também integram este Contrato...
                    2.3. A partir da assinatura deste...
                    2.4. Em caso de divergência...
                    2.5. Eventuais obrigações complementares..."

                **Exemplo (saída):**
                    [
                     "clause_number": "2.1", "content": "Constituem parte integrante..." ,
                     "clause_number": "2.2", "content": "Também integram este Contrato...",
                     "clause_number": "2.3", "content": "A partir da assinatura deste..." ,
                     "clause_number": "2.4", "content": "Em caso de divergência..." ,
                     "clause_number": "2.5", "content": "Eventuais obrigações complementares..."
                    ]
                **Exemplo (saída incorreta — proibida):**
                [

                 "clause_number": "2",
                 "content": "Constituem parte integrante... Também integram este Contrato... A partir da assinatura... Em caso de divergência... Eventuais obrigações..."
                ]



            2. **Delimitação do conteúdo da cláusula**
            Para cada marcador principal `N` localizado:
            - Defina `clause_number = "N"` (padronize como `N`, `N.N` ou `N.N.N`, sem duplicar pontos finais).
            - O `content` é **todo o texto** a partir desse marcador até **antes** do próximo marcador principal subsequente.
            - Inclua no `content`:
                - O corpo textual imediatamente após `N`.
                - **Todos os subitens pertencentes a `N`**, como listas `a)`, `b)`, `i)`, `ii)`, `1)`, `2)`, **desde que apareçam antes do próximo marcador principal**.

            **Exemplo (entrada):**
                1.2. A CONTRATADA executará os serviços conforme as especificações técnicas:
                    a) Escopo técnico.
                    b) Prazos de execução.
                    c) Critérios de aceite.
                1.3. O CONTRATANTE deverá...

            **Exemplo (saída):**
                ```json
                [
                "clause_number": "1.2",
                "content": "A CONTRATADA executará os serviços conforme as especificações técnicas:\\na) Escopo técnico.\\nb) Prazos de execução.\\nc) Critérios de aceite."
                ]

            3. **Subitens**
            - Subitens **não** geram registros separados. Devem ficar **concatenados no `content` da cláusula-pai**, preservando a ordem e a marcação literal (`a)`, `b)`, `i)`, `ii)`, etc.).
            - Sublistas dentro de subitens (por exemplo, `i)`, `ii)` dentro de `a)`) também **permanecem no `content`** da cláusula-pai.
            - Se houver uma sequência de subitens (`a)` … `p)`) após `28.2`, todos pertencem a `28.2` **até que** surja um novo marcador principal (`28.3`, `29.`, etc.).


            **Exemplo (entrada):**

              3.5. Obrigações:
                a) Segurança da informação:
                i) Criptografia ponta a ponta;
                ii) Registro de auditoria.
                b) Continuidade de negócios.
              4. Vigência.


            **Exemplo (saída):**
                ```json
                [
                 "clause_number": "3.5",
                 "content": "Obrigações:\\na) Segurança da informação:\\n   i) Criptografia ponta a ponta;\\n   ii) Registro de auditoria.\\nb) Continuidade de negócios."
                ]

            4. **Quebras de página e ruídos/artefatos**
            - Ignore cabeçalhos, rodapés, numeração de página, marcas e anotações tais como:
                - ``<!-- PageHeader="..." -->``
                - ``<!-- PageFooter="..." -->``
                - ``<!-- PageBreak -->``
                - "MINUTA APROVADA", nomes de diretoria, logotipos, números de versão, elementos de `<figure>…</figure>`.
            - Se esses elementos surgirem **dentro** da área de uma cláusula, **remova-os** do `content`.
            - Preserve informações jurídicas úteis presentes no corpo (incluindo e-mails, prazos, números de artigos) quando fizerem parte do texto da cláusula.

            **Exemplo (entrada):**

             <!-- PageHeader="Companhia X" -->
                28.2. Obrigações da CONTRATADA:
                a) Tratar dados pessoais conforme instruções do controlador;
             <!-- PageFooter="V8_01_07_2025" -->


            **Exemplo (saída):**
             [
             "clause_number": "28.2",
             "content": "Obrigações da CONTRATADA:\\na) Tratar dados pessoais conforme instruções do controlador;"
             ]


            5. **Títulos vs. cláusulas**
            - **Não** confundir títulos/cabeçalhos com a cláusula "de verdade".
            - Ignore títulos por extenso ou romanos (ex.: "Cláusula Décima Quarta", "XII") **como título**; use-os apenas para **descobrir e normalizar `clause_number`**.
            - Títulos como "3. DO OBJETO", "4. RESPONSABILIDADES" **não** são cláusulas por si; a cláusula válida é o corpo iniciado em `3.1`, `3.2` etc. Se houver somente `3.` com texto corrido logo após, trate `3` como cláusula e extraia o corpo normalmente.

             **Exemplo (entrada):**
                3. DO OBJETO
                3.1. A CONTRATADA fornecerá os serviços de suporte técnico...
                3.2. A CONTRATANTE deverá disponibilizar os acessos necessários..


             **Exemplo (saída):**
                [
                 "clause_number": "3", "content": "DO OBJETO" ,
                 "clause_number": "3.1", "content": "A CONTRATADA fornecerá os serviços de suporte técnico...",
                 "clause_number": "3.2", "content": "A CONTRATANTE deverá disponibilizar os acessos necessários..."
            ]


            6. **Texto antes do primeiro marcador**
            - Descarte todo texto antes do **primeiro** marcador principal do chunk.

            **Exemplo (entrada):**
                Preâmbulo, endereços e logotipos...
                1. Objeto do contrato
                A CONTRATADA...

            **Exemplo (saída):**
                [

                    "clause_number": "1",
                    "content": "Objeto do contrato\\nA CONTRATADA..."
                ]


            7. **Subitens "soltos" (sem pai visível)**
            - Se aparecerem subitens (`a)`, `b)`, `i)`) **sem** que exista um **marcador principal anterior claro** no texto disponível (página atual + até 3 seguintes), **não extraia** esses subitens.
            - Considere-os **ambíguos** e **ignore-os**.

            8. **Ordem e fidelidade**
            - Preserve rigorosamente a **ordem original**.
            - **Não reescreva** o texto; apenas remova ruídos (cabeçalho/rodapé/figuras).
            - Normalize espaços em branco excessivos e quebras de linha duplicadas.

            **Exemplo (entrada):**
                4.1. Obrigações da CONTRATADA:

                A) Manter equipe qualificada.
                B) Atender SLAs críticos.

                4.2. Multas.


            **Exemplo (saída):**

            [

                "clause_number": "4.1",
                "content": "Obrigações da CONTRATADA:\\n\\nA) Manter equipe qualificada.\\nB) Atender SLAs críticos.",

                "clause_number": "4.2",
                "content": "Multas."

            ]

        **Exemplos integrados:**

            Exemplo integrado 1 — 1.2 com subitens a)–i):

              **(entrada):**

                1.2. Para todos os fins contratuais aplicáveis, a expressão "Fornecimento Contratado" ou "Fornecimento" significa, conforme o objeto disposto expressamente no item 2 do Termo de Contratação, seus Anexos ou Pedido de Compra, de forma alternativa ou conjunta:
                    a) Aquisição de Bens.
                    b) Contratação de Serviços.
                    c) Contratação de Bens e Serviços.
                    d) Contratação de Serviços de Instalação e/ou Manutenção.
                    e) Contratação de Field Service (Empreiteiras).
                    f) Contratação de Serviços de Manutenção.
                    g) Contratação de Serviços de Ativação de Dados.
                    h) Licença de Uso de Software.
                    i) Consultoria.
              **(saída):**
                 [

                    "clause_number": "1.2",
                    "content": "Para todos os fins contratuais aplicáveis, ..."

                 ]

            Exemplo integrado 2 — 28.2 com a)–p) atravessando páginas, seguido de 28.3 e 28.4:
                **(entrada):**

                    28.2. Sem prejuízo das demais obrigações previstas nas Normas de Proteção de Dados Pessoais, a
                    CONTRATADA se obriga a:
                    a) Tratar Dados Pessoais nas hipóteses autorizadas...
                    ...
                    p) Transparência e prestação de contas...
                    <!-- PageFooter="V8_01_07_2025" -->
                    <!-- PageBreak -->
                    28.3. Eliminação: os Dados Pessoais tratados...
                    28.4. Comunicados e notificações...

                **(saída):**
                      "clauses": [
                        "clause_number": "28.2", "content": "Sem prejuízo das demais obrigações...",
                        "clause_number": "28.3", "content": "Eliminação: os Dados Pessoais...",
                        "clause_number": "28.4", "content": "Comunicados e notificações..."
                    ]

        """

        data = f"""
        Páginas do contrato:
        {chunk["content"]}
        """

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": data},
        ]

        response = safe_parse_with_retry(client, messages, response_format, config)

        total_prompt += response.usage.prompt_tokens
        total_completion += response.usage.completion_tokens
        total_tokens += response.usage.total_tokens

        structured_output = response.choices[0].message.parsed
        filtered_clauses[i] = json.loads(structured_output.model_dump_json(indent=2))
        i += 1

    return {
        "clauses": filtered_clauses,
        "usage": {
            "prompt": total_prompt,
            "completion": total_completion,
            "total": total_tokens,
        },
    }


def filter_clauses_for_training(chunks, client, response_format, config):
    """
    Extract clauses for training data. Handles both numeric and letter-based
    clause numbering, extracts sub-items separately (unlike production filtering).

    Parameters:
        chunks (list[dict]): Each dict must contain 'page_number' and 'content'.
        client (AzureOpenAI): Initialized GPT-4o client.
        response_format: Pydantic model for structured output.
        config (dict): Model parameters.

    Returns:
        dict: {"clauses": {page_number: PageOutput, ...}, "usage": {...}}
    """
    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    filtered_clauses = {}

    for chunk in chunks:
        prompt = """
            Você é um doutor especializado em análise de documentos jurídicos empresariais.

            Sua tarefa:

            - Extraia SOMENTE cláusulas, sub-cláusulas e subitens contratuais com base na estrutura de numeração principal (ex.: "3.", "3.5.", "4.1.2.") e subitens (ex.: "a.", "b.", "i.", "ii.").
            - Alguns templates que voce vai receber a estrutura de numeração principal da cláusula será por letras (ex.: "A.", "B.", "C.") e subitens por número (ex.: "A.", "A.1.", "A.2.")

            REGRAS:

            1. Tanto cláusulas (formato "X.") como sub-cláusulas (formato "X.Y.", "X.Y.Z.") e subitens (formato "a.", "b." etc.) devem ser extraídos separadamente.

            2. Se um subitem aparecer "solto" (ex.: sem número pai no mesmo chunk), ainda assim extraia-o separadamente, conforme requerido na regra 7.

            3. Preserve rigorosamente a numeração original e a sequência do texto.

            4. Se o número da cláusula vier por extenso ou em algarismos romanos (ex.: "Cláusula Décima Quarta", "XII"), converta sempre para numeração decimal pontuada (ex.: "14.", "12.").

            5. Ignore o título textual (nome da cláusula) e foque apenas na numeração e no seu conteúdo.

            6. Não se esqueça de sempre seperar se a clausula ou subclausula tiver subitens, jamais junte todos os subitens em uma clausula só.

            7. Se a pagina tiver as cláusulas em portugues e inglês, sempre pegue a parte em português. Se tiver somente em inglês, extraia em inglês.
        """

        data = f"""
        Página do contrato:
        {chunk["content"]}

        **Por favor não ignore subitens soltos mesmo que não seja possivel identificar a clausula pai, liste-os normalmente como "clause_number".
        **Ignore titulos de cláusulas e não confunda-os como uma clausula em si conforme requerido na regra 4."
        """

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": data},
        ]

        response = safe_parse_with_retry(client, messages, response_format, config)

        total_prompt += response.usage.prompt_tokens
        total_completion += response.usage.completion_tokens
        total_tokens += response.usage.total_tokens

        structured_output = response.choices[0].message.parsed
        filtered_clauses[int(chunk["page_number"])] = json.loads(
            structured_output.model_dump_json(indent=2)
        )

    return {
        "clauses": filtered_clauses,
        "usage": {
            "prompt": total_prompt,
            "completion": total_completion,
            "total": total_tokens,
        },
    }
