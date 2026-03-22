"""
Shared test fixtures for the Norma test suite.

Fixtures are reusable test setup components. Define them here
so any test file can use them without duplication.
"""

import pytest


@pytest.fixture
def sample_clauses():
    """A minimal set of clauses for testing pipeline functions."""
    return [
        {"clause_number": "3.1.", "content": "A CONTRATADA deverá manter os registros..."},
        {"clause_number": "3.2", "content": "O CONTRATANTE deverá disponibilizar..."},
        {"clause_number": " 4.1. ", "content": "Multas aplicáveis conforme regulamento."},
    ]


@pytest.fixture
def sample_extracted_pages():
    """Simulates the output of filter_clauses_with_gpt4o (multi-page extraction)."""
    return {
        "clauses": {
            "0": {
                "page_number": 1,
                "clauses": [
                    {"clause_number": "3.1.", "content": "Short version of clause 3.1"},
                    {"clause_number": "3.2", "content": "Clause 3.2 content"},
                ],
            },
            "1": {
                "page_number": 2,
                "clauses": [
                    {"clause_number": "3.1.", "content": "Longer version of clause 3.1 with more details"},
                    {"clause_number": "4.1", "content": "Clause 4.1 content"},
                ],
            },
        }
    }


@pytest.fixture
def sample_reviewed_clauses():
    """Simulates reviewed clauses for normalize_clause_numbers testing."""
    return {
        "3.1": {
            "clauses": [
                {
                    "numero_da_clausula": "3.1.",
                    "clasula_original": "Original text",
                    "problema_juridico": "Issue found",
                    "clausula_revisada": "Revised text",
                }
            ]
        },
        "4.": {
            "clauses": [
                {
                    "numero_da_clausula": "4.2",
                    "clasula_original": "Another clause",
                    "problema_juridico": "Another issue",
                    "clausula_revisada": "Another revision",
                }
            ]
        },
    }
