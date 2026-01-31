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
- Retrieval: simple TF-IDF-like vector index over paper paragraphs and code excerpts (no external embedding service) (`backend/app/vector_index.py`, `backend/app/main.py`).
- LLM adapter: OpenAI-compatible HTTP API calls controlled via env vars; answers cached into per-project QA log + summary (`backend/app/llm.py`, `backend/app/config.py`, `backend/app/storage.py`).

**Frontend**
- Vite + React + TypeScript UI (`frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/App.tsx`).
- Frontend calls backend at a hardcoded base URL: `http://localhost:8000` (`frontend/src/api.ts`).
- Dev server port: `5173` (`frontend/vite.config.ts`).

**Storage Layout**
- `projects/<project_id>/project.json` for per-project metadata (`backend/app/storage.py`).
- `projects/<project_id>/paper/paper.pdf` and `projects/<project_id>/paper/parsed.json` for raw PDF and parsed paragraphs (`backend/app/main.py`).
- `projects/<project_id>/paper/vector_index.json` for paper paragraph retrieval index (`backend/app/main.py`).
- `projects/<project_id>/code/repo/` for cloned repository (`backend/app/main.py`, `backend/app/code_ingest.py`).
- `projects/<project_id>/code/index.json`, `projects/<project_id>/code/symbols.json`, `projects/<project_id>/code/text_index.json` for code indexing outputs (`backend/app/main.py`).
- `projects/<project_id>/code/vector_index.json` for code excerpt retrieval index (`backend/app/main.py`).
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

3) Run the API on port 8000 (matches `frontend/src/api.ts`):

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Notes:
- CORS is currently allowlisted to `http://localhost:5173` (`backend/app/main.py`).
- Runtime state is written under `projects/` and to `backend/app.db` (`backend/app/config.py`).

**Frontend (Vite + React)**

```bash
cd frontend
npm ci
npm run dev
```

- Vite dev server runs on port `5173` (`frontend/vite.config.ts`).

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
- `backend/app/llm.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `backend/app/storage.py`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/styles.css`
