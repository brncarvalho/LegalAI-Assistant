from pydantic import BaseModel, Field
from typing import List, Optional

class Clause(BaseModel):
    """
    Represents a single contract clause as produced by the model.

    Attributes:
        clause_title (str): The title or heading of the clause.
        clause_number (str): The clause identifier, taken from the 'numero_da_clausula' field.
        content (str): The clause body text, taken from the 'conteudo' field.
    """
    #clause_title: str  # title or heading of the clause
    clause_number: str = Field(..., alias="numero_da_clausula")  # identifier for the clause
    content: str = Field(..., alias="conteudo")  # full text of the clause


class PageOutput(BaseModel):
    """
    Represents the clauses extracted from a single page of a document.

    Attributes:
        page_number (int): The 1-based page number in the document.
        clauses (List[Clause]): List of Clause objects found on this page.
    """
    page_number: int  # the page index from which clauses were extracted
    clauses: List[Clause]  # list of Clause models for this page


class ReviewedClause(BaseModel):
    """
    Schema for a clause after legal review by the model.

    Attributes:
        numero_da_clausula (str): The original clause number.
        clasula_original (str): The original clause text before review.
        problema_juridico (str): Description of the legal issue identified.
        clausula_revisada (str): The clause text after suggested legal revision.
    """
    numero_da_clausula: str  # original clause identifier
    clasula_original: str  # original clause text
    problema_juridico: str  # identified legal problem
    clausula_revisada: str  # revised clause text
    # clausula_alterada: str  # (optional) track specific alterations if needed


class PageReviewedOutput(BaseModel):
    """
    Contains all reviewed clauses for a single document page.

    Attributes:
        clauses (List[ReviewedClause]): List of clauses with review metadata.
    """
    clauses: List[ReviewedClause]  # list of ReviewedClause models for this page