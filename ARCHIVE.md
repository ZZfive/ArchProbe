# Archive

## Snapshot: Initial Backend + Frontend Scaffold

**Backend**
- FastAPI app with SQLite metadata store and project filesystem layout.
- Project endpoints: create, list, get detail, ingest paper, fetch summary.
- Paper ingest: resolves arXiv PDF, downloads file, hashes, parses into paragraph JSON.
- Code ingest: clone repo, capture commit hash, file index, symbol map, text excerpt index.
- Alignment: paragraph-to-code candidate matching with evidence and confidence.
- LLM adapter: API/local switch, evidence-backed answers, QA caching.

**Frontend**
- Vite + React + TypeScript scaffold.
- UI for project list, create form, project detail, ingest trigger, and summary display.
- QA form and history panel.
- Code index trigger.

**Storage Layout**
- `projects/<project_id>/paper` for PDF and parsed JSON.
- `projects/<project_id>/code` for repo clone and indices.
- `projects/<project_id>/alignment/map.json` for alignment results.
- `projects/<project_id>/summary/project_summary.md` for accumulated notes.
- `projects/<project_id>/qa/qa_log.jsonl` for question history and evidence.

**Key Files**
- `backend/app/main.py`
- `backend/app/ingest.py`
- `backend/app/code_ingest.py`
- `backend/app/alignment.py`
- `backend/app/llm.py`
- `backend/app/db.py`
- `backend/app/storage.py`
- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/styles.css`
