# AGENTS.md

Guidance for agentic coding tools working in this repository.

## Repo Layout

- `backend/`: FastAPI service (Python) providing the API and writing runtime state.
- `frontend/`: Vite + React + TypeScript UI.
- Runtime data (not source-of-truth): `projects/` and `backend/app.db` (gitignored).

Local dev URLs:
- Frontend: http://localhost:5173 (Vite may auto-increment to 5174)
- Backend: http://localhost:8000
- OpenAPI: http://localhost:8000/docs

Remote dev (VSCode SSH / Port Forwarding):
- Frontend runs on the server, but your browser is local.
- Do NOT hardcode `http://localhost:8000` in the frontend unless 8000 is also forwarded.
- Default behavior: frontend calls backend via relative `/projects/...` and Vite proxy forwards to `127.0.0.1:8000`.
- Optional: set `VITE_API_BASE` to an address reachable by the browser (e.g. forwarded backend port).

## Build / Lint / Test

### Frontend (Node)

From `frontend/`:
- Install deps: `npm ci`
- Dev server: `npm run dev`
- Prod build (includes typecheck): `npm run build` (runs `tsc -b && vite build`)
- Preview build: `npm run preview`

Notes:
- No dedicated `lint` or unit-test scripts currently.
- Dev proxy is configured in `frontend/vite.config.ts` for `/projects` → `http://127.0.0.1:8000`.

### Backend (Python)

From repo root:
- Create venv: `python -m venv .venv`
- Activate: `source .venv/bin/activate`
- Install deps: `pip install -r backend/requirements.txt`

Run API (from `backend/`):
- `uvicorn app.main:app --reload --port 8000`

GPU acceleration (FAISS / embeddings):
- FAISS GPU is installed via conda in CUDA environments (recommended):
  - `conda create -n archprobe-backend python=3.11 -y`
  - `conda activate archprobe-backend`
  - `conda install -c pytorch faiss-gpu -y`
  - `pip install -r backend/requirements-gpu.txt`
- Env toggles:
  - `FAISS_USE_GPU=auto|1|0` (default `auto`)
  - `FASTEMBED_DEVICE=auto|cuda|cpu` (default `auto`)
  - Offline embedding cache: set `FASTEMBED_CACHE_DIR` (or `FASTEMBED_CACHE_PATH`) and enforce `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`

Basic “lint/health” commands (current state):
- `python -m compileall backend/app`
- Optional typecheck: `python -m basedpyright backend/app` (no strict config; treat as advisory)

Proxy pitfall:
- Dev shells may export `HTTP_PROXY/HTTPS_PROXY` which can break localhost curl.
- Use `curl --noproxy '*' http://127.0.0.1:8000/projects` when debugging locally on the server.

### Verification (Manual QA)

There is a small manual QA runner (no external deps):
- `tests/qa/qa_runner.py` runs a question set against `/projects/{id}/ask-stream` and saves JSON.

Example:
```bash
python tests/qa/qa_runner.py --project-id <PROJECT_ID> --in tests/qa/qa_set.json --out tests/qa/runs/latest.json
```

Running a single test (future convention):
- Python/pytest: `pytest path/to/test_file.py::test_name` or `pytest -k "substring"`
- JS/Vitest: `vitest path/to/file.test.ts -t "test name"`

## Environment Variables

Backend LLM config (optional; without `LLM_API_KEY` answers may be placeholders):
- `LLM_PROVIDER` (default `api`)
- `LLM_API_BASE` (default `https://api.openai.com/v1`)
- `LLM_API_KEY` (default empty)
- `LLM_MODEL` (default `gpt-4o-mini`)

Index/ingest limits:
- `CODE_INDEX_MAX_FILES`, `CODE_INDEX_MAX_TOTAL_BYTES`, `CODE_INDEX_MAX_FILE_BYTES`
- `CODE_INDEX_IGNORE_DIRS`, `CODE_INDEX_IGNORE_EXTS`
- `PAPER_MAX_PDF_BYTES`, `PAPER_MAX_PAGES`, `PAPER_MAX_PARAGRAPHS`

Frontend:
- `VITE_API_BASE` (optional; if set, must be reachable from the browser)

## Code Style / Conventions

### General

- Prefer small, focused diffs; avoid opportunistic refactors while fixing bugs.
- Do not treat `projects/`, `backend/app.db`, `backend/.venv/`, `frontend/node_modules/` as source-of-truth.
- Keep JSON output stable: use `indent=2` and `ensure_ascii=True` unless the file already differs.

### Python (backend)

Imports:
- Group imports: stdlib → third-party → local (relative) imports.
- Prefer explicit relative imports: `from .config import ...`.

Typing:
- Prefer Python 3.10+ style (`list[...]`, `dict[...]`, `X | None`) when adding new code.
- Avoid `Any` unless handling unstructured JSON; keep boundaries narrow.

FastAPI patterns:
- Raise `HTTPException(status_code=..., detail=...)` for client-visible errors.
- Map external failures precisely (e.g. `requests.RequestException` → 502).
- Ensure resources are closed (`try/finally`) for sqlite/files.

I/O:
- Always specify `encoding="utf-8"`.
- For large/binary reads, follow `backend/app/code_ingest.py` safe-read patterns.

Shelling out:
- Be careful with destructive git operations used for cloned repos (reset/clean).

### TypeScript / React (frontend)

Type checking:
- `strict: true`; keep types explicit and avoid implicit `any`.

Imports:
- External imports first, then local.

API layer:
- Use relative `/projects/...` by default (works with Vite proxy + port forwarding).
- Backend JSON uses snake_case fields (`paper_url`, `repo_url`).
- On errors, prefer surfacing backend `detail` when present.

Components:
- Prefer functional components.
- Handle async errors explicitly (`try/catch`, `err instanceof Error`).
- Keep state minimal; compute derived state via `useMemo` when needed.

## Cursor / Copilot Instructions

- No Cursor rules found (`.cursor/rules/` or `.cursorrules`).
- No Copilot instructions found (`.github/copilot-instructions.md`).
