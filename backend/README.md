# CrisisGrid backend

This backend contains the PDF and repository ingestion pipeline used to create a validated experiment specification.

## Setup

From the repo root:

```bash
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

## Environment variables

Create a `.env` file with values for:

- `GROQ_API_KEY`
- `PINECONE_API_KEY`
- `PINECONE_INDEX`
- `DATABASE_URL`
- `ARTIFACTS_DIR`

## Endpoints

- `POST /experiments/ingest`
  - Form fields: `file`, `repo_url`, `branch`, `commit_ref`
  - `file` is optional if you only want to ingest a GitHub repo URL, and `repo_url` is optional if you only upload a PDF.
- `GET /experiments/{experiment_id}`
- `GET /experiments/{experiment_id}/spec`
- `GET /experiments/{experiment_id}/evidence`
- `GET /experiments/{experiment_id}/discrepancies`
- `POST /experiments/{experiment_id}/retrieve`
  - JSON body: `{"question": "How was the model trained?"}`; defaults to 8 matches (maximum 20).
  - Optional `top_k` sets the number of matches. Retrieval always searches paper chunks; Groq distinguishes paper-reported facts from clearly labeled inferences based on the paper's method and general knowledge when details are missing.

## Test with a PDF and GitHub repo

Start the app:

```bash
cd backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Upload a PDF and repository URL:

```bash
curl -X POST "http://localhost:8000/experiments/ingest" \
  -F "file=@C:/path/to/paper.pdf" \
  -F "repo_url=https://github.com/octocat/hello-world"
```

Or ingest a GitHub repo without a PDF:

```bash
curl -X POST "http://localhost:8000/experiments/ingest" \
  -F "repo_url=https://github.com/octocat/hello-world"
```

Then fetch the generated experiment JSON:

```bash
curl "http://localhost:8000/experiments/{experiment_id}/spec"
```

Retrieve relevant chunks for a question about that experiment's paper:

```bash
curl -X POST "http://localhost:8000/experiments/{experiment_id}/retrieve" \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"How was the model trained?\"}"
```

## Notes

- PDF parsing uses Docling when available and falls back to a text-based extraction path.
- Repository inspection validates GitHub URLs and inspects README/config files without executing code.
- The resulting experiment JSON is stored under `data/experiments/<experiment_id>/experiment_spec.json`.
- No SQLite metadata persistence is used; the generated data folder is the source of truth.
