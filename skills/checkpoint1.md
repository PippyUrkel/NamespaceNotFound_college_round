# Checkpoint 1

## Goal
Create the ingestion and experiment-specification backend for CrisisGrid using a PDF upload and GitHub repository link.

## Status
Completed: the backend can accept a PDF and/or GitHub repository URL, inspect the repo without executing code, parse the uploaded PDF, extract basic experiment metadata, compare values, build a deterministic DAG, and write the generated experiment specification to artifacts only.

## Files created or updated
- backend/app/injestor/__init__.py
- backend/app/injestor/config.py
- backend/app/injestor/models.py
- backend/app/injestor/parser.py
- backend/app/injestor/repo_inspector.py
- backend/app/injestor/extractor.py
- backend/app/injestor/comparison.py
- backend/app/injestor/feasibility.py
- backend/app/injestor/dag.py
- backend/app/injestor/service.py
- backend/app/injestor/routes.py
- backend/app/main.py
- backend/main.py
- backend/config.py
- backend/README.md
- backend/.env.example

## Validation
Passed:
- pytest backend/tests/test_ingestion.py -q
- Result: 6 passed

## Notes
- SQLite metadata persistence was removed by design; artifacts are the source of truth.
- The workflow supports file-only, repo-only, and combined ingest requests.
- Repository inspection validates GitHub URLs and does not execute code.
