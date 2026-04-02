# Norma - AI-Powered Legal Contract Review

Norma is a serverless AI pipeline that automatically reviews legal contract clauses against a curated knowledge base of previously approved contracts. It identifies legal misalignments, suggests minimal corrections, and generates annotated Word documents — reducing manual legal review time from hours to minutes.

Built for a real corporate legal department, the system integrates with Microsoft 365 (SharePoint, Teams, Power Automate) to provide an end-to-end workflow from document upload to reviewed output.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution Overview](#solution-overview)
- [Architecture](#architecture)
- [Knowledge Base Strategy](#knowledge-base-strategy)
- [Microsoft 365 Integration](#microsoft-365-integration)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Pipeline Workflow](#pipeline-workflow)
- [Output](#output)
- [Key Design Decisions](#key-design-decisions)
- [Setup](#setup)

---

## Problem Statement

Corporate legal teams spend significant time manually reviewing contracts clause by clause, checking whether each one aligns with the company's previously approved legal standards. This process is:

- **Time-consuming** — a single contract can take hours of review
- **Inconsistent** — different reviewers may apply different standards
- **Hard to scale** — as contract volume grows, the team becomes a bottleneck

## Solution Overview

Norma automates this review by combining **Retrieval-Augmented Generation (RAG)** with Azure's serverless infrastructure:

1. A contract PDF is uploaded to SharePoint
2. Power Automate sends it to Azure Blob Storage
3. Azure Durable Functions orchestrates the full review pipeline
4. Each clause is compared against similar approved clauses from the knowledge base
5. An LLM (GPT-4o) evaluates legal alignment and suggests minimal corrections
6. Original and revised Word documents are generated and sent back via Power Automate
7. The user is notified in Microsoft Teams when the review is complete

The key principle is **minimal intervention** — the AI doesn't rewrite clauses from scratch. It identifies specific legal gaps (missing liability caps, absent exceptions, conflicting obligations) and adjusts only what's necessary to restore compliance with approved standards.

---

## Architecture

```
                          Microsoft 365 Ecosystem
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   SharePoint          Power Automate           Microsoft Teams       │
│   (file upload)  ───► (2 flows: send &  ◄───►  (notifications +     │
│                        receive files)           Copilot Studio bot)  │
│                                                                      │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Azure Cloud                                   │
│                                                                      │
│   Blob Storage ──► Durable Functions (Orchestrator)                  │
│   (trigger)         │                                                │
│                     ├─► 1. Document Intelligence (PDF extraction)     │
│                     ├─► 2. GPT-4o (clause filtering)                 │
│                     ├─► 3. AI Search (retrieve similar clauses)       │
│                     ├─► 4. GPT-4o (legal review with RAG context)    │
│                     └─► 5. Document generation (.docx output)        │
│                                                                      │
│   AI Search Index                                                    │
│   (knowledge base: ~40 approved contracts, indexed by clause)        │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Knowledge Base Strategy

The knowledge base is the core of Norma's review quality. Instead of relying on generic legal knowledge, it uses **real contracts that were previously reviewed, approved, and signed** by the company's legal department.

### How it was built

- **~40 approved contracts** from multiple service types were collected
- Each contract was split into **individual clauses** (not pages or paragraphs)
- Each clause was embedded and indexed into **Azure AI Search** as a separate chunk

### Why clause-level indexing matters

When the AI reviews a clause — say, an "Object" clause — the vector search retrieves **similar "Object" clauses from multiple different contracts**. This gives the model a diverse set of approved examples for the same type of clause, rather than just one contract's version.

This approach means:

- The model sees how the legal department has handled similar clauses across different service contexts
- It can identify patterns and standards that hold across contracts
- The review is grounded in actual approved legal language, not generated text

The goal is never to replace the clause text, but to **infer corrections in light of how similar clauses were approved in the past**.

---

## Microsoft 365 Integration

Norma is designed to fit into the existing corporate workflow without requiring users to learn new tools.

### SharePoint

Users upload contract PDFs to a designated SharePoint folder — the same way they already share documents.

### Power Automate

Two dedicated flows handle the integration:

1. **Upload flow** — detects new files in SharePoint and sends the PDF to Azure Blob Storage for processing
2. **Output flow** — monitors the Azure output container and delivers the reviewed documents (original + revised) back to SharePoint

### Microsoft Teams

- A **notification channel** alerts users when:
  - Azure has received a contract and started processing
  - The reviewed documents are ready for download
- A **Copilot Studio bot** allows users to review individual clauses on-demand through Teams chat, using the same knowledge base as the main pipeline — useful for quick checks without submitting a full contract

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Orchestration** | Azure Durable Functions (Python) | Coordinate multi-step async pipeline |
| **PDF Extraction** | Azure Document Intelligence | Extract structured text from contract PDFs |
| **LLM** | Azure OpenAI (GPT-4o) | Clause filtering, legal review, structured output |
| **Vector Search** | Azure AI Search | Retrieve similar approved clauses (RAG) |
| **Embeddings** | Azure OpenAI (text-embedding-ada-002) | Clause vectorization for semantic search |
| **Storage** | Azure Blob Storage | PDF input, JSON intermediaries, .docx output |
| **Document Gen** | python-docx + lxml | Word documents with redline annotations |
| **Validation** | Pydantic v2 | Structured output schemas, config validation |
| **Integration** | Power Automate + SharePoint + Teams | End-to-end corporate workflow |
| **Chatbot** | Microsoft Copilot Studio | Single-clause review via Teams |

---

## Project Structure

```
LegalFunctionApp/
├── function_app.py                 # Entry point — Durable Functions orchestrator
├── host.json                       # Azure Functions runtime configuration
├── requirements.txt                # Production dependencies
├── requirements-dev.txt            # Development tools (pytest, ruff)
├── pyproject.toml                  # Project metadata & tooling config
│
├── models/                         # Pydantic data models
│   ├── models.py                  # Core models (Clause, PageOutput, ReviewedClause)
│   ├── rag.py                     # RAG pipeline schemas
│   └── search.py                  # Search request/response models
│
├── src/
│   ├── config/
│   │   ├── settings.py            # Centralized config via Pydantic BaseSettings
│   │   └── prompts.py             # LLM prompt templates (Portuguese legal domain)
│   │
│   ├── services/
│   │   ├── blob_storage.py        # Azure Blob Storage operations
│   │   ├── extract.py             # PDF extraction via Document Intelligence
│   │   ├── rag.py                 # RAG pipeline (clause extraction + review)
│   │   ├── search.py              # Azure AI Search vector queries
│   │   ├── embedding.py           # Text embedding generation
│   │   ├── indexing.py            # Search index creation & management
│   │   ├── document_generation.py # Word document output with annotations
│   │   └── token_tracker.py       # LLM token usage tracking
│   │
│   └── utils/
│       ├── chunking.py            # Page overlap & clause normalization
│       └── deduplication.py       # Merge duplicate clauses from overlaps
│
└── scripts/
    └── word_formating_VM.py       # Standalone redline formatting (Windows)
```

---

## Pipeline Workflow

The orchestrator (`function_app.py`) coordinates 5 stages using Azure Durable Functions:

### Stage 1 — Extraction

A PDF upload to Blob Storage triggers the pipeline. **Azure Document Intelligence** extracts the document content as Markdown, split by page. A page overlap strategy (configurable) ensures clauses that span page boundaries aren't lost.

### Stage 2 — Clause Filtering (Parallel)

Pages are sent to **GPT-4o** in parallel chunks of 5. The model identifies and extracts individual clauses with their numbers and content, returning **Pydantic-validated structured output**. Overlapping clauses from the page overlap are then deduplicated, keeping the longest (most complete) version.

### Stage 3 — Legal Review with RAG (Parallel)

Each extracted clause goes through the RAG pipeline:

1. **Vector search** retrieves the top 5 most similar approved clauses from the knowledge base
2. These reference clauses are injected into the prompt as context
3. **GPT-4o** evaluates the clause against the references, classifying it as:
   - **Aligned** — matches approved standards, no changes needed
   - **Partially aligned** — minor gap (e.g., missing liability cap), targeted insertion
   - **Misaligned** — conflicts with standards, minimal correction applied

Clauses are processed in parallel chunks for throughput.

### Stage 4 — Document Generation

Two Word documents are generated:
- **Original document** — the contract clauses as extracted
- **Revised document** — clauses with suggested corrections applied

### Stage 5 — Usage Tracking

Token usage metrics (prompt, completion, total) are recorded per contract for cost monitoring.

---

## Output

For each processed contract, Norma produces:

| Output | Format | Description |
|--------|--------|-------------|
| Original document | `.docx` | Extracted clauses in their original form |
| Revised document | `.docx` | Clauses with legal corrections applied |
| Usage metrics | `.json` | Token consumption for cost tracking |

Each reviewed clause includes:
- **Clause number** — original numbering preserved
- **Original text** — unmodified clause
- **Legal issue** — description of the identified problem (if any)
- **Revised text** — corrected clause with minimal changes

---

## Key Design Decisions

### Why Azure Durable Functions?

Contract review involves multiple sequential and parallel steps with external API calls that can take minutes. Durable Functions provide:
- **Orchestration** — define the full workflow as code, not config
- **Parallel fan-out** — process clause chunks concurrently
- **Automatic retry and state management** — handled by the framework
- **Serverless scaling** — no idle infrastructure costs

### Why Pydantic for structured output?

Using Pydantic models as `response_format` in OpenAI's API guarantees the LLM returns data matching the expected schema. This eliminates fragile regex/JSON parsing and catches schema violations at the API level.

### Why Pydantic BaseSettings for configuration?

Instead of scattered `os.getenv()` calls, all configuration lives in a single typed `Settings` class that:
- Validates all environment variables at startup (fail fast)
- Provides IDE autocomplete and type safety
- Creates a single source of truth for configuration

### Why clause-level chunking instead of page-level?

Legal review is inherently clause-by-clause. Page boundaries are arbitrary. By extracting individual clauses, the vector search retrieves semantically relevant comparisons (e.g., object clause vs. object clause), not just text that happened to be on a similar page.

### Why dependency injection in activities?

Each Durable Function activity instantiates its own service clients rather than sharing module-level instances. This follows Azure Functions' stateless execution model and makes each activity independently testable.

---

## Setup

### Prerequisites

- Python 3.11+
- Azure subscription with the following services:
  - Azure Functions
  - Azure OpenAI (GPT-4o + text-embedding-ada-002 deployments)
  - Azure Document Intelligence
  - Azure AI Search
  - Azure Blob Storage

### Installation

```bash
cd LegalFunctionApp
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in `LegalFunctionApp/` with:

```env
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
EMBEDDINGS_OPENAI_ENDPOINT=https://your-embeddings.openai.azure.com/
EMBEDDINGS_OPENAI_API_KEY=your-key
AZURE_AI_DOC_INTELLIGENCE_ENDPOINT=https://your-doc-intel.cognitiveservices.azure.com/
AZURE_AI_DOC_INTELLIGENCE_API_KEY=your-key
AZURE_AI_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_AI_SEARCH_API_KEY=your-key
AZURE_WEB_JOBS_STORAGE=DefaultEndpointsProtocol=https;AccountName=...
AZURE_OPENAI_RESOURCE_URL=https://your-openai.openai.azure.com/
INDEX_NAME=your-index-name
```

### Running locally

```bash
func start
```

---

## License

This project was built for portfolio and demonstration purposes.
