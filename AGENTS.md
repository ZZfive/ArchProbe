# AGENTS.md

This file is guidance for agentic coding tools working in this repository.

## Repo layout

- `backend/`: FastAPI service (Python) providing the API and writing runtime state.
- `frontend/`: Vite + React + TypeScript UI.
- Runtime data (not source): `projects/` and `backend/app.db` (both are gitignored).

Key ports / URLs (local dev):

- Frontend: http://localhost:5173 (`frontend/vite.config.ts`)
- Backend: http://localhost:8000 (`frontend/src/api.ts` hardcodes API base)
- Backend OpenAPI: http://localhost:8000/docs

## Build / lint / test commands

### Frontend (Node)

From `frontend/`:

- Install deps: `npm ci`
- Dev server: `npm run dev`
- Production build (includes typecheck): `npm run build` (runs `tsc -b && vite build`)
- Preview production build: `npm run preview`

Notes:

- There is no `lint` or `test` script in `frontend/package.json` today.

### Backend (Python)

From repo root:

- Create venv: `python -m venv .venv`
- Activate: `source .venv/bin/activate`
- Install deps: `pip install -r backend/requirements.txt`

Run the API (from `backend/`):

- `uvicorn app.main:app --reload --port 8000`

Notes:

- No test/lint tooling is defined in-repo (no pytest/ruff/black configs, no CI workflows).
- Backend CORS allows loopback dev origins (localhost/127.0.0.1/[::1]) on any port (Vite may move from 5173 to 5174 if 5173 is taken).

### Running a single test (current state)

Not currently applicable: the repo does not ship a test runner configuration.

If/when tests are added, prefer these conventional invocations:

- Python/pytest: `pytest path/to/test_file.py::test_name` or `pytest -k "substring"`
- JS/Vitest: `vitest path/to/file.test.ts -t "test name"`

## Environment variables (backend)

LLM configuration is optional; without `LLM_API_KEY` the app returns placeholder answers.

- `LLM_PROVIDER` (default: `api`)
- `LLM_API_BASE` (default: `https://api.openai.com/v1`)
- `LLM_API_KEY` (default: empty)
- `LLM_MODEL` (default: `gpt-4o-mini`)

Index/ingest limits (useful for large inputs):

- `CODE_INDEX_MAX_FILES`, `CODE_INDEX_MAX_TOTAL_BYTES`, `CODE_INDEX_MAX_FILE_BYTES`
- `CODE_INDEX_IGNORE_DIRS`, `CODE_INDEX_IGNORE_EXTS`
- `PAPER_MAX_PDF_BYTES`, `PAPER_MAX_PAGES`, `PAPER_MAX_PARAGRAPHS`

## Code style and conventions

### General

- Do not treat `projects/`, `backend/app.db`, `backend/.venv`, or `frontend/node_modules/` as source-of-truth.
- Prefer small, focused diffs; avoid refactors while fixing bugs.
- Keep JSON outputs stable: this repo typically writes JSON with `indent=2` and `ensure_ascii=True`.

### Python (backend)

Imports:

- Group imports as: stdlib, third-party, local (relative) imports.
- Local imports typically use explicit relative form, e.g. `from .config import ...`.

Typing:

- The codebase is mixed (both `typing.List`/`Dict` and `list[...]`/`dict[...]` exist).
- For new code, prefer Python 3.10+ style (`list[...]`, `dict[...]`, `X | None`) unless editing a file that already uses the older style.
- Avoid weakening types to `object`/`Any` unless you are genuinely dealing with unstructured JSON.

FastAPI patterns:

- Raise `fastapi.HTTPException(status_code=..., detail=...)` for client-visible errors.
- Catch and map external failures precisely (e.g. `requests.RequestException` -> 502).
- Ensure resources are closed with `try/finally` (e.g. SQLite connections).

Error handling:

- Prefer narrow exceptions; if cleanup is required, cleanup then re-raise.
- Avoid silent failures; if you must ignore an exception (e.g. best-effort delete), keep the scope minimal.

I/O and encoding:

- Use explicit UTF-8 when reading/writing text (`encoding="utf-8"`).
- When reading potentially binary/large files, follow `backend/app/code_ingest.py` style (`_safe_read_text`).

Shelling out:

- `backend/app/code_ingest.py` uses `subprocess.run(..., check=True)` and interacts with `git`.
- Be careful with destructive git operations on cloned repos (it does `reset --hard origin/HEAD`).

### TypeScript / React (frontend)

Type checking:

- `frontend/tsconfig.json` is `strict: true` and builds run `tsc -b`.
- Prefer types that survive strict mode; avoid implicit `any`.

Imports:

- Keep external imports first, then relative local imports.

API layer:

- `frontend/src/api.ts` wraps `fetch` and throws on non-2xx responses.
- API payload fields are snake_case to match backend JSON (e.g. `paper_url`, `repo_url`).

Component patterns:

- Prefer functional components.
- Handle async errors explicitly (`try/catch` with `err instanceof Error` checks).
- Keep UI state minimal and derived values computed via `useMemo` when needed.

## Cursor / Copilot instructions

No Cursor rules found (`.cursor/rules/` or `.cursorrules`).
No Copilot instructions found (`.github/copilot-instructions.md`).

If you add those later, mirror them here (or link to them) so agentic tools follow the same constraints.
