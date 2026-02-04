# Iteration Plan: Accurate Hybrid QA + Structured Learning Notes

This plan turns the analysis into concrete milestones with acceptance criteria and a change list. It is ordered to fix answer accuracy first, then improve learning retention.

## Scope
- Target: paper+code QA accuracy, code snippet relevance, and structured learning notes.
- Out of scope: full MLOps training pipelines, UI redesign, new external dependencies.

## Milestone 0: Baseline + Telemetry (1-2 days)

Status: DONE (2026-02-03)

### Goals
- Establish a small, repeatable QA set and visible failure signals.

### Deliverables
- A local QA dataset (20-30 queries) covering: paper-only, code-only, hybrid, and ambiguous questions.
- Basic instrumentation for evidence source mix and confidence.

### Verification
- Documented QA set and expected outcomes.
- Ability to run QA set and inspect evidence mix.

### Change List
- Add a small QA runner script (no new deps) that calls `/ask-stream` and saves results to JSON for review.

Implemented:
- `tests/qa/qa_set.json`
- `tests/qa/README.md`
- `tests/qa/qa_runner.py`

## Milestone 1: Query Router + Evidence Gating (highest impact)

Status: DONE (2026-02-03)

### Goals
- Stop forcing paper-code binding; route queries by intent.
- Filter low-quality evidence and surface lack of evidence explicitly.

### Design
- Router output: `paper_only | code_only | hybrid | fallback`.
- Router decision: rules-first with optional LLM fallback (small prompt, low temperature).
- Evidence gating: minimum relevance threshold; if below, do not pass into prompt.
- Prompt change: allow partial inference but require explicit "insufficient evidence" notice.

### Verification
- Router correctness on QA set: >= 80% correct routing by manual review.
- For code-only queries, evidence contains >= 70% code sources.
- For paper-only queries, evidence contains >= 70% paper sources.
- When evidence is insufficient, answer includes an explicit missing-evidence statement.

### Change List
- `backend/app/main.py`: add router decision step; split retrieval into paper and code buckets; apply evidence thresholds; pass router result to prompt.
- `backend/app/llm.py`: update prompt to allow limited inference with explicit missing-evidence reporting.
- `frontend/src/App.tsx`: show router result + evidence mix (paper vs code %) per answer.

Implemented:
- `backend/app/main.py`
- `backend/app/llm.py`
- `frontend/src/api.ts`
- `frontend/src/App.tsx`

## Milestone 2: Code Retrieval Precision (symbol-chunk indexing)

### Goals
- Make code snippets relevant by indexing at symbol granularity.

### Design
- Build code "chunks" per symbol (function/class) using line ranges from `symbols.json`.
- Use symbol chunks for code vector/BM25 retrieval rather than file head excerpts.
- Keep fallback to file-level excerpt when symbol range missing.

### Verification
- QA set: code-only queries return at least 1 correct code snippet 80% of the time.
- "Wrong file" snippet rate reduced by >= 50% vs baseline.

### Change List
- `backend/app/code_ingest.py`: emit symbol chunk index entries (path, start_line, end_line, text).
- `backend/app/vector_index.py` + `backend/app/bm25_index.py`: accept symbol chunk docs.
- `backend/app/main.py`: build code docs from symbol chunks for retrieval; include chunk metadata in evidence.
- `backend/app/schemas.py`: extend evidence fields if needed to include chunk ranges.

## Milestone 3: Alignment as Auxiliary Signal (no forced binding)

### Goals
- De-noise alignment evidence; treat it as optional, not mandatory.

### Design
- Only include alignment matches when confidence exceeds threshold.
- Limit alignment contribution to a small slice of evidence (e.g., max 20%).

### Verification
- For paper-only questions, alignment evidence should not override paper retrieval.
- Alignment-derived evidence should not appear in top-3 unless above confidence threshold.

### Change List
- `backend/app/alignment.py`: expose confidence score in a normalized float.
- `backend/app/main.py`: gate alignment evidence by confidence and cap its contribution.

## Milestone 4: Structured Learning Notes (avoid repeated questions)

### Goals
- Produce structured study artifacts from QA history to aid review.

### Design
- Generate `notes.json` with sections: concepts, implementation, open_questions, flashcards.
- Export `notes.md` summary with links to code snippets and key paper paragraphs.
- Trigger generation: on-demand via API or after N QA entries.

### Verification
- A project with QA history produces `notes.json` and `notes.md` without errors.
- Notes include at least one item per section when relevant data exists.

### Change List
- `backend/app/storage.py`: add read/write for notes files.
- `backend/app/main.py`: add endpoints: `GET/POST /projects/{id}/notes`.
- `backend/app/llm.py`: add prompt template for notes extraction from QA log.
- `frontend/src/App.tsx`: add Notes tab with download/export.

## Milestone 5: Learning Path + Review Scheduling

### Goals
- Turn notes into a guided learning path and review schedule.

### Design
- Generate learning path graph from concepts and dependencies.
- Simple spaced-repetition schedule fields in notes (intervals).

### Verification
- Notes contain a `learning_path` array and `review_schedule` entries.

### Change List
- `backend/app/learning.py`: path generation and schedule updates.
- `frontend/src/App.tsx`: render path and review reminders.

## Global Acceptance Criteria
- No regression in existing pipeline steps (ingest/index/align/vectors).
- For the QA set, overall answer correctness improves by >= 30% vs baseline.
- Code snippet relevance improves by >= 50% (manual scoring).
- Notes export is available and stable.

## Verification Commands
- `python -m compileall backend/app`
- `cd frontend && npm run build`
