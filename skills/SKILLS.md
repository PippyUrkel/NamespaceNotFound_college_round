# CrisisGrid

CrisisGrid is an AI-powered research reproducibility platform. It takes an AI/ML paper (PDF or arXiv link) and optionally the authors' GitHub repo, converts the methodology into an executable, versioned experiment graph, runs it, verifies the paper's claims, audits reproducibility risks, and produces an evidence-linked report.

The experiment graph is the core data structure. Verification, versioning, auditing and reporting all hang off it.

## Working agreement

- The audit module is the current focus. Prefer changes inside `audit/` and avoid editing other modules unless asked. If the audit needs something from another module, state the contract you need rather than rewriting that module.
- Ask before adding a new dependency, changing the shared data models, or changing a database table.
- Make small, reviewable changes. Run the tests for the area you touched before saying a task is done.
- If a requirement is unclear, ask one short question instead of guessing.

## Ground rules for the whole project

1. **Provenance on every value.** Each extracted field carries a source (`paper`, `code`, `assumed`, `missing`), an evidence pointer and a confidence. Never fill a missing value silently.
2. **Versions are immutable.** Editing a node creates a new version with a parent link. Never mutate a saved version.
3. **Evidence on every finding and verdict.** Anything shown to a user must link back to a paper section, a file and line, or a run.
4. **Be honest about limits.** If a critical field is missing or the dataset or compute is unavailable, the verdict is `Not verifiable` with the reason.
5. **Engine before AI.** Deterministic logic comes first; the LLM handles only what rules cannot.

## Stack and layout

FastAPI backend, Pydantic models, SQLite for the demo (Postgres later), Docker for execution, Claude API for extraction and LLM audit checks, Next.js with React Flow on the frontend. The layout below is a proposal; follow the actual repo structure if it differs.

```
backend/
  app/
    ingest/      paper + repo parsing, LLM extraction into the spec
    graph/       nodes, config hashing, immutable versions, diff
    runner/      topological execution, caching, multi-seed, Docker
    audit/       rules, LLM checks, risk score   <- current focus
    report/      evidence-linked report
  main.py
  config.py
  tests/
frontend/
```

## Commands

These are typical defaults. Check the repo for the real ones and update this section.

```
pip install -r requirements.txt
uvicorn backend.main:app --reload
pytest backend/tests/audit
```

## The audit module

### What it audits

Whether a paper's results can be independently reproduced, not whether the science is good. It looks for anything that would stop someone else from getting the same number, or that makes the claimed number untrustworthy.

Four inputs:

- The paper text (is everything needed to repeat the experiment stated?)
- The code repo (can it be set up and run?)
- Paper versus code (do they agree?)
- Our reproduction runs (does the claim survive when run?)

### Shape of the module

- The audit is a pure function. It receives a context object and a phase, and returns a list of findings. It never reads or writes the database, never calls the runner, and never modifies its input.
- The backend builds the context, stores the findings and triggers the audit. Keep that glue outside `audit/`.
- Rules are small, single-purpose functions registered with a phase. One rule asks one question and returns zero or more findings.
- Context contains: the spec (fields with provenance), the paper text, the repo path (may be absent), and run summaries (only in the run phase).

### Two phases

- **static**: runs right after ingest using only the paper, spec and repo. Fast. This is the only phase available for papers that cannot be executed.
- **run**: runs after the verdict is computed and adds findings based on real results, such as the gap to the claim and seed variance versus the claimed improvement.

The audit runs per version, not per paper, because edits can change findings. Findings are replaced per version and per phase, so a rerun never wipes static findings.

### Findings

Every finding has: rule id, severity (`low`, `medium`, `high`, `critical`), status (`confirmed` or `possible`), title, message, a list of evidence items, and an optional remediation.

- `confirmed` is for exact checks, such as an unpinned dependency or a field marked missing.
- `possible` is for heuristics, such as hints of test-set leakage. Static analysis cannot prove leakage, so word these findings accordingly.
- A finding without evidence must not be produced.
- Separate "missing" (not stated) from "conflicting" (paper and code disagree) with different rule ids.

### Rules to implement, in order

1. Critical field missing (dataset, model, learning rate, epochs, metric)
2. Missing seed (spec says missing and no seed call found in the repo)
3. No variance reported (no std, confidence interval or multiple runs in the paper)
4. Unpinned dependencies, and missing requirements file
5. Paper versus code mismatch (only where both values exist)
6. Dataset unavailable (link check with a timeout)
7. Test set used for tuning (heuristic, `possible`)
8. No code available, plus a count of `missing` and `assumed` spec fields
9. Run phase: reproduced mean far from claim, and seed variance larger than the claimed improvement

### No repo case

Many papers publish no code. Rules that need the repo must skip cleanly, not error. Add the "no code available" finding. When runs come from our own reimplementation, run-phase messages must say that the run used assumed values, so results are not over-read.

### LLM checks

Use the LLM only for fuzzy questions: ambiguous metric definitions, claims without baselines, hints of leakage.

- Require structured output with a verbatim quote, a section and a confidence.
- Verify the quote appears in the paper text after normalizing whitespace and case. Drop the finding if it does not.
- Cap LLM findings at status `possible` and severity `medium`. The LLM must not be able to raise a critical finding alone.
- Run the LLM layer in the background; never block the static rules on it.

### Risk score

Sum severity weights per finding, count `possible` findings at half weight, and cap at 100. Always return the breakdown of which findings contributed. Bucket into low, medium and high for the UI. The score must be explainable.

## Testing

- Every rule has a unit test.
- Keep two fixture repos: a clean one that must produce zero findings, and a deliberately flawed one that triggers each rule exactly once.
- Test the no-repo path and the missing-field path for every rule.
- Test LLM checks with recorded responses, including one with a fabricated quote that must be dropped.

## Do not

- Make an audit rule depend on the database, network or runner.
- Show a score or finding without its evidence.
- Claim a result is reproduced or not reproduced when the right verdict is `Not verifiable`.
- Let the LLM produce a high-severity or confirmed finding by itself.
- Execute untrusted repository code outside the Docker sandbox.
