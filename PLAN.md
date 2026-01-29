# Execution Plan

## Phase 2: Project Memory + QA Loop (Done)
1. Add QA log persistence (JSONL per project).
2. Add backend endpoints for asking questions and retrieving QA history.
3. Append meaningful QA entries to the project summary document.
4. Add frontend UI for asking questions and viewing QA history.

## Phase 3: Code Ingest + Indexing (Done)
1. Clone/pull repo and compute commit hash.
2. Build file list, basic symbol map, and text index.
3. Store code index and metadata in project cache.

## Phase 4: Alignment + Evidence (Done)
1. Candidate matching (paper paragraphs to code snippets).
2. Evidence map and confidence scoring.

## Phase 5: LLM Integration (Done)
1. Adapter layer for API + local models.
2. Answer generation with evidence grounding.
3. Caching and re-use of answers.

## Phase 6: Evidence UX + Retrieval
1. Rank evidence by match score and paragraph confidence.
2. Show evidence in QA history UI.
3. Add vector retrieval for code excerpts and paper paragraphs.
