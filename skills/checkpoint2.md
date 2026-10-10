# Checkpoint 2

## Scope

This checkpoint continues the ingestion-focused backend work for CrisisGrid. The goal was to confirm the app boots correctly, keep the artifact-based workflow, and preserve the ingestion + chunking + feasibility flow without moving into retrieval.

## Completed

- Verified the import/startup issue is fixed for the backend app when launched via `uvicorn main:app --reload`.
- Kept the environment configuration in `backend/config.py` using `dotenv` and the default Pinecone index name set to `bnb`.
- Confirmed the output storage is artifact-based and points to the `backend/data` directory rather than any SQLite metadata store.
- Validated the ingestion route behavior and the generated experiment artifact flow.
- Reviewed the current ingestion API in `backend/app/injestor/routes.py` and confirmed it supports PDF upload and GitHub repo inspection without retrieval logic.
- Ran the focused backend test suite and confirmed the relevant ingestion checks pass.

## Key files

- `backend/config.py` — environment-driven configuration with `.env` loading and default `bnb` index
- `backend/app/injestor/routes.py` — API endpoints for upload/ingest and artifact retrieval
- `backend/app/injestor/service.py` — orchestration of paper/repo analysis and artifact generation
- `backend/app/injestor/vector_store.py` — chunking and Pinecone indexing logic
- `backend/app/injestor/feasibility.py` — feasibility classification logic
- `backend/data/` — current artifact storage directory for experiment results

## Validation status

- `pytest` smoke test: passed
- App startup smoke check: passed
- Health endpoint response: `{"status": "ok"}`

## Notes

- Retrieval is still intentionally out of scope for this checkpoint.
- The backend is intentionally artifact-only and does not persist metadata in SQLite.
- The current app remains focused on: paper ingestion, repo inspection, chunk creation, Pinecone indexing when configured, and feasibility assessment.
