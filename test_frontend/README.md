# CrisisGrid Testing Studio (`test_frontend`)

A modern, responsive interactive visualizer for testing and inspecting the full **CrisisGrid Reproducibility Pipeline**.

---

## Quick Start

### 1. Start the Backend API (FastAPI)
From the project root:
```bash
uv run --project backend uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
API health check: `http://localhost:8000/health`

### 2. Start the Frontend Dev Server
From `test_frontend/`:
```bash
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Features & Visualizations

1. **Overview & Ingestion Hub (`/experiments/ingest`)**:
   - Ingest research paper PDFs (with PyPDF2 / Docling OCR fallback) and GitHub repositories.
   - Click **Quick Demo** to immediately generate a reproducible experiment pipeline in 1 click.
   - Inspect extracted parameters, reconciled values, confidence percentages, and discrepancy warnings (paper vs repository).
   - Pinecone vector indexing status.

2. **Experiment Graph (DAG) Inspector (`/experiments/{id}/graph`)**:
   - Visual execution flow showing isolated nodes in topological order (`setup_environment` $\rightarrow$ `data_pipeline` $\rightarrow$ `model_initialization` $\rightarrow$ `training_pipeline` $\rightarrow$ `evaluation_pipeline` $\rightarrow$ `claim_verification`).
   - Click any node to inspect its exact executable container code, input parameters, and provenance tags (`repository`, `paper`, `reconciled`, `assumed`, `tuned`).
   - **Parameter Tuning Modal**: Edit learning rate, batch size, epochs, random seed, or custom node code. Submitting generates an immutable new version (`v1` $\rightarrow$ `v2`).
   - **Version Diff Viewer**: Compare parameters and side-by-side / unified code diffs between versions.

3. **Feasibility Assessment (`/experiments/{id}/feasibility`)**:
   - Pre-execution check verifying host resources (CPU cores, available RAM, free disk space, GPU acceleration, Docker daemon).
   - Displays verdict: `feasible`, `feasible_with_limitations`, or `blocked`.
   - Node-by-node memory, disk, GPU requirements, and estimated runtime.

4. **Multi-Seed Execution Runner (`/experiments/{id}/executions`)**:
   - Configure execution seeds (defaults to `42, 123, 7`), timeouts, memory limits, and CPU quotas.
   - Real-time progress log streaming (`node_start`, `node_complete`, `node_cache_hit`, `seed_complete`).
   - Independent seed cards showing status (`completed`, `timed_out`, `failed`, `resource_exhausted`), runtime, metrics pills, and expandable node-by-node logs (stdout/stderr).
   - Aggregated metrics table with mean, std dev, min, max (failed runs are never zero-biased).
   - "Retry / Resume Failed Seeds" and "Cancel" operations.

5. **Provenance & Audit Evidence (`/experiments/{id}/executions/{id}/evidence`)**:
   - Displays execution manifest hash, graph hash, resolved dependencies, and Docker digest.
   - Highlights the strict separation of execution status from scientific verdicts (hardware bounds or container crashes never imply that a paper's findings are false).
   - Full JSON manifest viewer with copy-to-clipboard.

6. **Audit & Report (`/experiments/{id}/audit/*`, `/experiments/{id}/report`)**:
   - Run the static audit (optionally with background LLM checks) and compare the latest execution against the paper's claimed results.
   - Each claim is **Reproducible** when the reproduced mean is within ±10% (relative) of the paper's value, otherwise **Not reproducible**.
   - Generate Report runs any missing audit phases and shows the verdict, risk score, evidence-linked findings, and limitations; `report.md` is downloadable.
