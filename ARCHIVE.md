# Archive

## Snapshot: Backend + Frontend

**Backend**
- FastAPI app with SQLite metadata store and a per-project filesystem layout (`backend/app/main.py`, `backend/app/db.py`, `backend/app/storage.py`).
- Project endpoints (selected):
  - Create/list/detail: `POST /projects`, `GET /projects`, `GET /projects/{project_id}` (`backend/app/main.py`).
  - Paper ingest: `POST /projects/{project_id}/ingest` (`backend/app/main.py`).
  - Code indexing: `POST /projects/{project_id}/code-index` (`backend/app/main.py`).
  - Alignment map: `POST /projects/{project_id}/align`, `GET /projects/{project_id}/alignment` (`backend/app/main.py`).
  - Vector indices (paper + code): `POST /projects/{project_id}/vector-index` (`backend/app/main.py`, `backend/app/vector_index.py`).
  - Q&A: `POST /projects/{project_id}/ask`, `GET /projects/{project_id}/qa` (`backend/app/main.py`).
  - Project summary: `GET /projects/{project_id}/summary` (`backend/app/main.py`).
- Paper ingest: resolves URL, downloads PDF, hashes it, parses into paragraphs JSON (`backend/app/ingest.py`, `backend/app/main.py`).
- Code ingest/indexing: clones repo via `git`, records commit hash, builds file index + symbol index + text excerpt index (`backend/app/code_ingest.py`, `backend/app/main.py`).
- Alignment: paragraph-to-code candidate matching with evidence and confidence (`backend/app/alignment.py`, `backend/app/main.py`).
- Retrieval: local lexical retrieval for paper/code via TF-IDF-like vectors + BM25 indices (no external embedding service) (`backend/app/vector_index.py`, `backend/app/bm25_index.py`, `backend/app/main.py`).
- LLM adapter: OpenAI-compatible HTTP API calls controlled via env vars; answers use structured evidence snippets with citations; Q&A cached into per-project QA log + summary (`backend/app/llm.py`, `backend/app/config.py`, `backend/app/storage.py`).

**Frontend**
- Vite + React + TypeScript UI (`frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`).
- Frontend calls backend at a hardcoded base URL: `http://localhost:8000` (`frontend/src/api.ts`).
- Dev server port: `5173` (`frontend/vite.config.ts`).

**Storage Layout**
- `projects/<project_id>/project.json` for per-project metadata (`backend/app/storage.py`).
- `projects/<project_id>/paper/paper.pdf` and `projects/<project_id>/paper/parsed.json` for raw PDF and parsed paragraphs (`backend/app/main.py`).
- `projects/<project_id>/paper/vector_index.json` for paper paragraph retrieval index (`backend/app/main.py`).
- `projects/<project_id>/paper/bm25_index.json` for paper BM25 index (`backend/app/main.py`).
- `projects/<project_id>/code/repo/` for cloned repository (`backend/app/main.py`, `backend/app/code_ingest.py`).
- `projects/<project_id>/code/index.json`, `projects/<project_id>/code/symbols.json`, `projects/<project_id>/code/text_index.json` for code indexing outputs (`backend/app/main.py`).
- `projects/<project_id>/code/vector_index.json` for code excerpt retrieval index (`backend/app/main.py`).
- `projects/<project_id>/code/bm25_index.json` for code BM25 index (`backend/app/main.py`).
- `projects/<project_id>/alignment/map.json` for alignment results (`backend/app/main.py`).
- `projects/<project_id>/qa/qa_log.jsonl` for question history, answers, and evidence (`backend/app/storage.py`).
- `projects/<project_id>/summary/project_summary.md` for accumulated notes (appends Q/A entries) (`backend/app/storage.py`).

**SQLite**
- DB path: `backend/app.db` (`backend/app/config.py`).

## How To Run (Local Dev)

**Prereqs**
- Python (for backend) and Node/npm (for frontend)
- `git` available on PATH (code indexing calls `git clone`/`git fetch`) (`backend/app/code_ingest.py`)

**Backend (FastAPI)**

1) Create a venv and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

2) Configure LLM env vars (optional but recommended):

- `LLM_PROVIDER` (default: `api`) (`backend/app/config.py`)
- `LLM_API_BASE` (default: `https://api.openai.com/v1`) (`backend/app/config.py`)
- `LLM_API_KEY` (default: empty string) (`backend/app/config.py`)
- `LLM_MODEL` (default: `gpt-4o-mini`) (`backend/app/config.py`)

Optional indexing/ingest limits (recommended for large repos/PDFs):

- `CODE_INDEX_MAX_FILES`, `CODE_INDEX_MAX_TOTAL_BYTES`, `CODE_INDEX_MAX_FILE_BYTES` (`backend/app/config.py`)
- `CODE_INDEX_IGNORE_DIRS`, `CODE_INDEX_IGNORE_EXTS` (`backend/app/config.py`)
- `PAPER_MAX_PDF_BYTES`, `PAPER_MAX_PAGES`, `PAPER_MAX_PARAGRAPHS` (`backend/app/config.py`)

3) Run the API on port 8000 (matches `frontend/src/api.ts`):

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Notes:
- CORS is currently allowlisted to loopback dev origins (localhost/127.0.0.1/[::1]) on any port (`backend/app/main.py`).
- Runtime state is written under `projects/` and to `backend/app.db` (`backend/app/config.py`).

**Frontend (Vite + React)**

```bash
cd frontend
npm ci
npm run dev
```

- Vite dev server runs on port `5173` (`frontend/vite.config.ts`).

## Quickstart: Happy Path Workflow

Once both services are running:

- Frontend UI: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Backend docs (OpenAPI): `http://localhost:8000/docs`

Happy path (API-only) with curl:

1) Create a project (paper + repo URLs are stored on the project record)

```bash
curl -sS -X POST "http://localhost:8000/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "demo",
    "paper_url": "https://arxiv.org/abs/2301.07041",
    "repo_url": "https://github.com/user/repo"
  }'
```

2) Ingest paper (downloads/parses based on the stored `paper_url`)

```bash
curl -sS -X POST "http://localhost:8000/projects/{project_id}/ingest"
```

3) Index code (clones based on the stored `repo_url`)

```bash
curl -sS -X POST "http://localhost:8000/projects/{project_id}/code-index"
```

4) Build retrieval indices (BM25 + TF-IDF-like for paper + code)

```bash
curl -sS -X POST "http://localhost:8000/projects/{project_id}/vector-index"
```

5) Generate alignment

```bash
curl -sS -X POST "http://localhost:8000/projects/{project_id}/align"
```

6) Ask a question

```bash
curl -sS -X POST "http://localhost:8000/projects/{project_id}/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "How does this code implement the paper method?"}'
```

Reset / cleanup:

- Clear a single project's cached files: `rm -rf projects/{project_id}/`
- Reset everything (all projects): `rm -rf projects/ backend/app.db`

## Network Configuration

**Port Hardcoding**
- Frontend API calls are hardcoded to `http://localhost:8000` (`frontend/src/api.ts`)
- Frontend dev server runs on port `5173` (`frontend/vite.config.ts`)
- Backend CORS is configured to allow origins from local loopback dev origins (see `backend/app/main.py`)

**Implications**
- Frontend will not work if backend runs on a different port or host without code changes
- Backend will reject requests from origins other than `localhost:5173`
- For custom deployments, update both `frontend/src/api.ts` and `backend/app/main.py` to match your desired ports/hosts

## LLM Configuration Behavior

**When `LLM_API_KEY` is missing or empty:**
- Q&A still runs, but returns a placeholder answer (no external LLM request is made)
- All other operations (ingest, index, align, retrieval) work normally

**When `LLM_PROVIDER=local`:**
- Not implemented yet (returns a placeholder answer)

**Default Behavior (API mode):**
- Uses OpenAI API (`https://api.openai.com/v1`) by default
- Requires valid `LLM_API_KEY` for successful requests
- Model defaults to `gpt-4o-mini`

## Troubleshooting

**Common Issues**

*CORS Errors*
- Frontend can't reach backend: Check that backend is running on port 8000 and frontend on port 5173
- Browser console shows CORS blocked: Verify `allow_origins` includes `http://localhost:5173` in `backend/app/main.py`

*Git/Code Indexing Issues*
- Code indexing fails: Ensure `git` is available on PATH and repository URL is accessible
- Large repos cause timeouts: Set `CODE_INDEX_MAX_FILES`, `CODE_INDEX_MAX_TOTAL_BYTES`, `CODE_INDEX_MAX_FILE_BYTES` limits

*PDF Ingestion Problems*
- Paper ingest fails: Check URL is accessible and PDF size is under `PAPER_MAX_PDF_BYTES` limit
- PDF parsing errors: Verify PDF isn't corrupted and page count is under `PAPER_MAX_PAGES` limit

*LLM/Question Answering*
- Q&A requests fail: Verify `LLM_API_KEY` is set and valid (for API mode) or local server is running (for local mode)
- Empty or generic responses: Check `LLM_MODEL` is supported by your provider and API base URL is correct

*Performance Issues*
- Slow indexing responses: Consider reducing indexing limits or excluding large directories with `CODE_INDEX_IGNORE_DIRS`
- Memory usage during indexing: Monitor RAM usage and implement file size limits for large codebases

*Database Issues*
- SQLite errors: Check `backend/app.db` file permissions and disk space
- Missing project data: Verify `projects/` directory exists and is writable

**Debug URLs**
- Backend API docs: http://localhost:8000/docs
- Frontend dev tools: Browser Developer Tools (F12) for network errors
- Project data inspection: Check files under `projects/{project_id}/` directory structure

## Notes / Gaps

- No Docker/Compose/Kubernetes entrypoints are present in the repo.
- No CI workflows are present.
- Tests/lint scripts are not configured in `frontend/package.json` and no backend test tooling is defined.

**Key Files**
- `backend/app/main.py`
- `backend/app/ingest.py`
- `backend/app/code_ingest.py`
- `backend/app/alignment.py`
- `backend/app/vector_index.py`
- `backend/app/bm25_index.py`
- `backend/app/llm.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/storage.py`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/styles.css`
