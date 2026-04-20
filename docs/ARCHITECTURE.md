# Architecture Overview

## Components
- **API Service (FastAPI):** CRUD and workflow endpoints.
- **Postgres:** system of record for claims/evidence/evaluations.
- **Worker Jobs:** extraction and enrichment tasks.
- **Frontend (planned):** candidate and claim transparency dashboard.

## Request Flow
1. Ingest statement text.
2. Extract candidate claims.
3. Attach evidence sources.
4. Human or policy-guided evaluation.
5. Score snapshot computation.
6. Publish queryable results.

## Design Principles
- Deterministic scoring with transparent formulas.
- Immutable source provenance where possible.
- Separation of extraction vs adjudication.
