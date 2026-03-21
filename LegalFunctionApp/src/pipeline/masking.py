from src import get_model_config
from src import get_openai_client


model_config = get_model_config()["openai_models"]["gpt_4o_mini"]

client = get_openai_client()


def masking_companies_with_gpt4o_mini(data, client):
    """
    Mask sensitive entities in contract clauses using GPT-4o Mini.

    Iterates over each clause in the provided data structure, sends a masking
    prompt to the LLM, and replaces the clause content with the masked version.

    Parameters:
        data (dict): Mapping of page identifiers to dicts containing a 'clauses'
                     list; each clause is a dict with a 'content' key.
        client:      An initialized AzureOpenAI client (GPT-4o Mini) with
                     a `chat.completions.create` method.

    Returns:
        dict: The same `data` structure, but with each clause's 'content'
              replaced by the masked output from the model.
    """

    # Loop over each page in the dataset
    for page in data.keys():
        # Loop over each clause entry on that page
        for clause in data[page]["clauses"]:
            # Build the system prompt with masking rules for various entity types
            prompt = """
                    Você é um assistente de pré‑processamento de texto. Substitua no texto abaixo qualquer instância de:
                    - Organizações / Empresas → [ORG]
                    - Partes do contrato (CONTRATANTE / CONTRATADA) → [PARTES]
                    - Datas (dd/mm/yyyy) → [DATA]
                    - CNPJs → [CNPJ]
                    - Software / Produtos → [PRODUTO]
                    - Ferramentas / Plataformas → [FERRAMENTA]
                    - URLs → [URL]
                    - Emails → [EMAIL]
                    - IDs de documento → [DOC_ID]
                    - Valores monetários → [QUANTIDADE]
                    - Percentuais → [PERCENTUAL]
                    - Endereços / Localizações → [LOCAL]
                    - Nome de contrato → 
                    - Nomes de pessoas → [PESSOA]
                    - Telefones → [TELEFONE]

                    **Exemplo 1**  
                    Entrada:  
                    CLÁUSULA PRIMEIRA – DO OBJETO  
                    Pelo presente instrumento, BRASILSEG COMPANHIA DE SEGUROS (CNPJ 28.196.889/0001‑43),  
                    doravante “CONTRATANTE”, e PTLS SERVIÇOS DE TECNOLOGIA (CNPJ 09.162.855/0005‑17),  
                    doravante “CONTRATADA”, em 01/03/2021 acordam o seguinte:

                    Saída:  
                    CLÁUSULA PRIMEIRA – DO OBJETO  
                    Pelo presente instrumento, [ORG] ([CNPJ]),  
                    doravante “[PARTES]”, e [ORG] ([CNPJ]),  
                    doravante “[PARTES]”, em [DATA] acordam o seguinte:

                    **Exemplo 2**  
                    Entrada:  
                    Os serviços incluem a implementação do Microsoft Endpoint Manager (Intune) e do SCCM.  
                    A documentação está em https://docs.example.com/endpoint.  
                    Para suporte, contate suporte@empresa.com ou ligue para (11) 91234‑5678.  
                    O valor contratual é de R$ 12.345,67 (doze mil, trezentos e quarenta e cinco reais),  
                    com reajuste anual de 5%.
                    Anexos e no CONTRATO RED HAT
                    Declaração Parceiro Red Hat.

                    Saída:  
                    Os serviços incluem a implementação do [PRODUTO] e do [PRODUTO].  
                    A documentação está em [URL].  
                    Para suporte, contate [EMAIL] ou ligue para [TELEFONE].  
                    O valor contratual é de [QUANTIDADE],  
                    com reajuste anual de [PERCENTUAL].
                    Anexos e no CONTRATO [ORG]
                    Declaração Parceiro [ORG].

                **Preste bem atenção para não esquecer de substituir nomes empresas, até mesmo as parceiras por ORG.    
            """

            # Build the user message with the actual clause content to mask
            content = f"""
            **Agora, aplique estas mesmas regras ao próximo trecho de contrato:**  
            {clause["content"]}
            """
            # Send the prompt and content to the LLM for masking
            response = client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": prompt,
                    },
                    {
                        "role": "user",
                        "content": content,
                    },
                ],
                max_tokens=model_config["max_tokens"],
                temperature=model_config["temperature"],
                top_p=model_config["top_p"],
                model=model_config["deployment"],
            )
            # Replace the clause's content with the masked output
            clause["content"] = response.choices[0].message.content

    # Return the updated data structure with masked clauses
    return data
