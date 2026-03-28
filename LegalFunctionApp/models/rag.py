from pydantic import BaseModel, Field


class RAGRequest(BaseModel):
    query: str
    limit: int = 5


class RAGResponse(BaseModel):
    query: str
    answer: str


class Clause(BaseModel):
    """
    Represents a single contract clause as produced by the model.

    Attributes:
        clause_title (str): The title or heading of the clause.
        clause_number (str): The clause identifier, taken from the 'numero_da_clausula' field.
        content (str): The clause body text, taken from the 'conteudo' field.
    """

    clause_number: str = Field(..., alias="numero_da_clausula")
    content: str = Field(..., alias="conteudo")


class PageOutput(BaseModel):
    """
    Represents the clauses extracted from a single page of a document.

    Attributes:
        page_number (int): The 1-based page number in the document.
        clauses (List[Clause]): List of Clause objects found on this page.
    """

    page_number: int
    clauses: list[Clause]


class ReviewedClause(BaseModel):
    """
    Schema for a clause after legal review by the model.

    Attributes:
        numero_da_clausula (str): The original clause number.
        clasula_original (str): The original clause text before review.
        problema_juridico (str): Description of the legal issue identified.
        clausula_revisada (str): The clause text after suggested legal revision.
    """

    numero_da_clausula: str
    clasula_original: str
    problema_juridico: str
    clausula_revisada: str


class PageReviewedOutput(BaseModel):
    """
    Contains all reviewed clauses for a single document page.

    Attributes:
        clauses (List[ReviewedClause]): List of clauses with review metadata.
    """

    clauses: list[ReviewedClause]
