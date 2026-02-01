import json
import heapq
import itertools
from pathlib import Path
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import PROJECTS_DIR
from .db import get_connection, init_db
from .code_ingest import (
    build_file_index,
    build_symbol_index,
    build_text_index,
    clone_or_update_repo,
    get_repo_hash,
    write_code_index,
    write_symbol_index,
    write_text_index,
)
from .alignment import build_alignment_map, write_alignment
from .vector_index import (
    build_vector_index,
    load_vector_index,
    query_vector_index,
    write_vector_index,
)
from .bm25_index import (
    build_bm25_index,
    load_bm25_index,
    query_bm25_index,
    write_bm25_index,
)
from .ingest import (
    download_pdf,
    file_sha256,
    parse_pdf_to_paragraphs,
    resolve_paper_url,
    write_parsed_json,
)
from .schemas import (
    AlignmentResponse,
    AlignmentGetResponse,
    AskRequest,
    AskResponse,
    CodeIndexResponse,
    IngestResponse,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
    VectorIndexResponse,
)
from .llm import LLMError, generate_answer
from .storage import (
    append_project_summary,
    append_qa_log,
    ensure_project_dirs,
    read_project_summary,
    read_qa_log,
    write_project_meta,
)


app = FastAPI(title="Paper-Code Align")

app.add_middleware(
    CORSMiddleware,
    # Local dev: browsers may use localhost, 127.0.0.1, or IPv6 loopback.
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
    ],
    # Vite may auto-increment the port (e.g. 5174) if 5173 is taken.
    # Allow any loopback origin on any port for local dev.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|\[::1\]):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()


def _row_to_project(row) -> ProjectOut:
    focus_points = json.loads(row["focus_points"]) if row["focus_points"] else None
    return ProjectOut(
        id=row["id"],
        name=row["name"],
        paper_url=row["paper_url"],
        repo_url=row["repo_url"],
        focus_points=focus_points,
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        paper_hash=row["paper_hash"],
        repo_hash=row["repo_hash"],
    )


@app.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate) -> ProjectOut:
    project_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    focus_points = json.dumps(payload.focus_points or [])

    ensure_project_dirs(project_id)
    write_project_meta(
        project_id,
        {
            "id": project_id,
            "name": payload.name,
            "paper_url": payload.paper_url,
            "repo_url": payload.repo_url,
            "focus_points": payload.focus_points or [],
            "created_at": now,
        },
    )

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO projects (id, name, paper_url, repo_url, focus_points, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                payload.name,
                payload.paper_url,
                payload.repo_url,
                focus_points,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return ProjectOut(
        id=project_id,
        name=payload.name,
        paper_url=payload.paper_url,
        repo_url=payload.repo_url,
        focus_points=payload.focus_points or [],
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
        paper_hash=None,
        repo_hash=None,
    )


@app.get("/projects", response_model=List[ProjectOut])
def list_projects() -> List[ProjectOut]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_project(row) for row in rows]


@app.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> ProjectDetail:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project = _row_to_project(row)
    return ProjectDetail(
        **project.model_dump(),
        paper_parsed_path=row["paper_parsed_path"],
        code_index_path=row["code_index_path"],
        alignment_path=row["alignment_path"],
    )


@app.get("/projects/{project_id}/summary")
def get_summary(project_id: str) -> dict:
    summary = read_project_summary(project_id)
    return {"project_id": project_id, "summary": summary}


@app.get("/projects/{project_id}/qa")
def get_qa_log(project_id: str) -> dict:
    entries = read_qa_log(project_id)
    return {"project_id": project_id, "entries": entries}


@app.post("/projects/{project_id}/ingest", response_model=IngestResponse)
def ingest_paper(project_id: str) -> IngestResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = ensure_project_dirs(project_id)
    parsed_path = project_dir / "paper" / "parsed.json"
    if row["paper_hash"] and parsed_path.exists():
        return IngestResponse(
            project_id=project_id,
            paper_hash=row["paper_hash"],
            parsed_path=str(parsed_path),
        )

    pdf_url = resolve_paper_url(row["paper_url"])
    if not (pdf_url.startswith("http://") or pdf_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Invalid paper URL")
    pdf_path = project_dir / "paper" / "paper.pdf"
    try:
        download_pdf(pdf_url, pdf_path)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except requests.RequestException as err:
        raise HTTPException(status_code=502, detail=f"Failed to fetch PDF: {err}")

    paper_hash = file_sha256(pdf_path)
    paragraphs = parse_pdf_to_paragraphs(pdf_path)
    write_parsed_json(
        parsed_path,
        {
            "source_url": pdf_url,
            "paper_hash": paper_hash,
            "paragraphs": paragraphs,
        },
    )

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE projects
            SET paper_hash = ?, paper_parsed_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (paper_hash, str(parsed_path), now, project_id),
        )
        conn.commit()
    finally:
        conn.close()

    return IngestResponse(
        project_id=project_id, paper_hash=paper_hash, parsed_path=str(parsed_path)
    )


@app.post("/projects/{project_id}/code-index", response_model=CodeIndexResponse)
def ingest_code(project_id: str) -> CodeIndexResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = ensure_project_dirs(project_id)
    repo_dir = project_dir / "code" / "repo"
    index_path = project_dir / "code" / "index.json"
    symbol_path = project_dir / "code" / "symbols.json"
    text_index_path = project_dir / "code" / "text_index.json"
    if row["repo_hash"] and index_path.exists():
        return CodeIndexResponse(
            project_id=project_id,
            repo_hash=row["repo_hash"],
            index_path=str(index_path),
        )

    clone_or_update_repo(row["repo_url"], repo_dir)
    repo_hash = get_repo_hash(repo_dir)
    file_index = build_file_index(repo_dir)
    file_paths = [repo_dir / entry["path"] for entry in file_index]
    symbol_index = build_symbol_index(repo_dir, file_paths)
    text_index = build_text_index(repo_dir, file_paths)
    write_code_index(
        index_path,
        {
            "repo_url": row["repo_url"],
            "repo_hash": repo_hash,
            "files": file_index,
            "symbols_path": str(symbol_path),
            "text_index_path": str(text_index_path),
        },
    )
    write_symbol_index(
        symbol_path,
        {
            "repo_hash": repo_hash,
            "symbols": symbol_index,
        },
    )
    write_text_index(
        text_index_path,
        {
            "repo_hash": repo_hash,
            "entries": text_index,
        },
    )

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE projects
            SET repo_hash = ?, code_index_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (repo_hash, str(index_path), now, project_id),
        )
        conn.commit()
    finally:
        conn.close()

    return CodeIndexResponse(
        project_id=project_id,
        repo_hash=repo_hash,
        index_path=str(index_path),
    )


@app.post("/projects/{project_id}/align", response_model=AlignmentResponse)
def align_project(project_id: str) -> AlignmentResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = ensure_project_dirs(project_id)
    parsed_path = project_dir / "paper" / "parsed.json"
    symbol_path = project_dir / "code" / "symbols.json"
    text_index_path = project_dir / "code" / "text_index.json"
    alignment_path = project_dir / "alignment" / "map.json"

    if (
        not parsed_path.exists()
        or not symbol_path.exists()
        or not text_index_path.exists()
    ):
        raise HTTPException(
            status_code=400, detail="Run paper ingest and code index first"
        )

    alignment = build_alignment_map(parsed_path, symbol_path, text_index_path)
    write_alignment(alignment_path, alignment)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE projects
            SET alignment_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (str(alignment_path), now, project_id),
        )
        conn.commit()
    finally:
        conn.close()

    raw_count = alignment.get("match_count", "0")
    if isinstance(raw_count, int):
        match_count = raw_count
    elif isinstance(raw_count, str) and raw_count.isdigit():
        match_count = int(raw_count)
    else:
        match_count = 0
    return AlignmentResponse(
        project_id=project_id,
        alignment_path=str(alignment_path),
        match_count=match_count,
    )


@app.post("/projects/{project_id}/vector-index", response_model=VectorIndexResponse)
def build_vector_indices(project_id: str) -> VectorIndexResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = ensure_project_dirs(project_id)
    parsed_path = project_dir / "paper" / "parsed.json"
    text_index_path = project_dir / "code" / "text_index.json"
    if not parsed_path.exists() or not text_index_path.exists():
        raise HTTPException(
            status_code=400, detail="Run paper ingest and code index first"
        )

    paper_data = json.loads(parsed_path.read_text(encoding="utf-8"))
    paper_docs = []
    for idx, paragraph in enumerate(paper_data.get("paragraphs", [])):
        paper_docs.append(
            {
                "doc_id": f"paper:{idx}",
                "text": paragraph.get("text", ""),
            }
        )

    code_data = json.loads(text_index_path.read_text(encoding="utf-8"))
    code_docs = []
    for entry in code_data.get("entries", []):
        code_docs.append(
            {
                "doc_id": f"code:{entry.get('path', '')}",
                "text": entry.get("excerpt", ""),
            }
        )

    paper_index = build_vector_index(paper_docs)
    code_index = build_vector_index(code_docs)
    paper_index_path = project_dir / "paper" / "vector_index.json"
    code_index_path = project_dir / "code" / "vector_index.json"
    write_vector_index(paper_index_path, paper_index)
    write_vector_index(code_index_path, code_index)

    paper_bm25 = build_bm25_index(paper_docs)
    code_bm25 = build_bm25_index(code_docs)
    paper_bm25_path = project_dir / "paper" / "bm25_index.json"
    code_bm25_path = project_dir / "code" / "bm25_index.json"
    write_bm25_index(paper_bm25_path, paper_bm25)
    write_bm25_index(code_bm25_path, code_bm25)

    return VectorIndexResponse(
        project_id=project_id,
        paper_index_path=str(paper_index_path),
        code_index_path=str(code_index_path),
        paper_bm25_path=str(paper_bm25_path),
        code_bm25_path=str(code_bm25_path),
    )


@app.get("/projects/{project_id}/alignment", response_model=AlignmentGetResponse)
def get_alignment(project_id: str) -> AlignmentGetResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    alignment_path_value = row["alignment_path"]
    if not alignment_path_value:
        return AlignmentGetResponse(
            project_id=project_id, alignment_path=None, alignment=None
        )
    alignment_path = Path(alignment_path_value)
    if not alignment_path.exists():
        return AlignmentGetResponse(
            project_id=project_id, alignment_path=str(alignment_path), alignment=None
        )
    data = json.loads(alignment_path.read_text(encoding="utf-8"))
    return AlignmentGetResponse(
        project_id=project_id, alignment_path=str(alignment_path), alignment=data
    )


@app.post("/projects/{project_id}/ask", response_model=AskResponse)
def ask_project(project_id: str, payload: AskRequest) -> AskResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    focus_points = []
    raw_focus = row["focus_points"]
    if raw_focus:
        try:
            parsed = json.loads(raw_focus)
            if isinstance(parsed, list):
                focus_points = [str(item) for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            focus_points = []

    now = datetime.now(timezone.utc).isoformat()
    existing = read_qa_log(project_id)
    for entry in existing:
        if (
            entry.get("question", "").strip().lower()
            == payload.question.strip().lower()
        ):
            created_at = entry.get("created_at") or now
            raw_confidence = entry.get("confidence", 0.0)
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError):
                confidence = 0.0
            return AskResponse(
                project_id=project_id,
                question=entry.get("question", payload.question),
                answer=entry.get("answer", ""),
                confidence=confidence,
                created_at=datetime.fromisoformat(created_at),
            )
    alignment_path = row["alignment_path"]
    evidence = []
    if alignment_path:
        alignment_file = Path(alignment_path)
        if alignment_file.exists():
            alignment = json.loads(alignment_file.read_text(encoding="utf-8"))
            evidence = _collect_evidence(alignment)

    paper_vector_path = Path(
        ensure_project_dirs(project_id) / "paper" / "vector_index.json"
    )
    code_vector_path = Path(
        ensure_project_dirs(project_id) / "code" / "vector_index.json"
    )
    project_dir = ensure_project_dirs(project_id)
    parsed_path = project_dir / "paper" / "parsed.json"
    text_index_path = project_dir / "code" / "text_index.json"
    paper_paragraphs: list[dict] = []
    code_excerpts: dict[str, str] = {}
    if parsed_path.exists():
        try:
            paper_data = json.loads(parsed_path.read_text(encoding="utf-8"))
            raw_paragraphs = paper_data.get("paragraphs", [])
            if isinstance(raw_paragraphs, list):
                paper_paragraphs = raw_paragraphs
        except json.JSONDecodeError:
            paper_paragraphs = []
    if text_index_path.exists():
        try:
            code_data = json.loads(text_index_path.read_text(encoding="utf-8"))
            for entry in code_data.get("entries", []):
                path = entry.get("path")
                excerpt = entry.get("excerpt")
                if path and excerpt and path not in code_excerpts:
                    code_excerpts[str(path)] = str(excerpt)
        except json.JSONDecodeError:
            code_excerpts = {}
    query_text = payload.question
    if focus_points:
        query_text = query_text + "\n\nFocus points: " + ", ".join(focus_points)
    paper_vec_matches: list[tuple[str, float]] = []
    code_vec_matches: list[tuple[str, float]] = []
    if paper_vector_path.exists():
        paper_index = load_vector_index(paper_vector_path)
        paper_vec_matches = query_vector_index(paper_index, query_text, top_k=5)
    if code_vector_path.exists():
        code_index = load_vector_index(code_vector_path)
        code_vec_matches = query_vector_index(code_index, query_text, top_k=5)

    paper_bm25_path = project_dir / "paper" / "bm25_index.json"
    code_bm25_path = project_dir / "code" / "bm25_index.json"
    paper_bm25_matches: list[tuple[str, float]] = []
    code_bm25_matches: list[tuple[str, float]] = []
    if paper_bm25_path.exists():
        paper_bm25 = load_bm25_index(paper_bm25_path)
        paper_bm25_matches = query_bm25_index(paper_bm25, query_text, top_k=5)
    if code_bm25_path.exists():
        code_bm25 = load_bm25_index(code_bm25_path)
        code_bm25_matches = query_bm25_index(code_bm25, query_text, top_k=5)

    for doc_id, score in _rrf_fuse(
        [("tfidf", paper_vec_matches), ("bm25", paper_bm25_matches)], top_k=3
    ):
        ev = {"kind": "paper_hybrid", "doc_id": doc_id, "score": score}
        if isinstance(doc_id, str) and doc_id.startswith("paper:"):
            raw_idx = doc_id.split(":", 1)[1]
            if raw_idx.isdigit():
                idx = int(raw_idx)
                if 0 <= idx < len(paper_paragraphs):
                    paragraph = paper_paragraphs[idx]
                    ev["paragraph_index"] = str(idx)
                    ev["page"] = str(paragraph.get("page", ""))
                    ev["text_excerpt"] = str(paragraph.get("text", ""))[:240]
        evidence.append(ev)

    for doc_id, score in _rrf_fuse(
        [("tfidf", code_vec_matches), ("bm25", code_bm25_matches)], top_k=3
    ):
        ev = {"kind": "code_hybrid", "doc_id": doc_id, "score": score}
        if isinstance(doc_id, str) and doc_id.startswith("code:"):
            rel = doc_id.split(":", 1)[1]
            if rel:
                ev["path"] = rel
                ev["excerpt"] = code_excerpts.get(rel, "")[:240]
        evidence.append(ev)

    evidence = _dedup_evidence(evidence)

    try:
        response = generate_answer(
            payload.question, evidence, focus_points=focus_points or None
        )
        answer = str(response.get("answer", ""))
        raw_confidence = response.get("confidence", 0.0)
        if isinstance(raw_confidence, (int, float)):
            confidence = float(raw_confidence)
        elif isinstance(raw_confidence, str):
            try:
                confidence = float(raw_confidence)
            except ValueError:
                confidence = 0.0
        else:
            confidence = 0.0
    except LLMError as err:
        # LLMError is already user-facing.
        answer = str(err)
        confidence = 0.0

    entry = {
        "question": payload.question,
        "answer": answer,
        "evidence": evidence,
        "confidence": confidence,
        "created_at": now,
    }
    append_qa_log(project_id, entry)
    append_project_summary(
        project_id, [f"Q: {payload.question}", f"A: {answer}", "---"]
    )

    return AskResponse(
        project_id=project_id,
        question=payload.question,
        answer=answer,
        confidence=confidence,
        created_at=datetime.fromisoformat(now),
    )


def _collect_evidence(alignment: dict) -> list[dict]:
    limit = 20
    # heap items are compared lexicographically; include a monotonic counter so ties
    # on (score, paragraph_confidence) never fall back to comparing dict entries.
    heap: list[tuple[tuple[int, float], int, dict]] = []
    counter = itertools.count()
    for item in alignment.get("results", []):
        for match in item.get("matches", []):
            raw_score = match.get("score", "0")
            if isinstance(raw_score, int):
                score = raw_score
            elif isinstance(raw_score, str) and raw_score.isdigit():
                score = int(raw_score)
            else:
                score = 0
            raw_conf = item.get("confidence", "0")
            if isinstance(raw_conf, str):
                try:
                    paragraph_confidence = float(raw_conf)
                except ValueError:
                    paragraph_confidence = 0.0
            elif isinstance(raw_conf, (int, float)):
                paragraph_confidence = float(raw_conf)
            else:
                paragraph_confidence = 0.0
            entry = {
                "paragraph_index": item.get("paragraph_index"),
                "page": item.get("page"),
                "text_excerpt": item.get("text_excerpt"),
                "paragraph_confidence": paragraph_confidence,
                "kind": match.get("kind"),
                "path": match.get("path"),
                "name": match.get("name"),
                "line": match.get("line"),
                "score": score,
                "matched_tokens": match.get("matched_tokens"),
                "excerpt": match.get("excerpt"),
            }
            key = (score, paragraph_confidence)
            if len(heap) < limit:
                heapq.heappush(heap, (key, next(counter), entry))
            else:
                heapq.heappushpop(heap, (key, next(counter), entry))

    top = [item for _, __, item in sorted(heap, key=lambda pair: pair[0], reverse=True)]
    return top


def _dedup_evidence(items: list[dict]) -> list[dict]:
    seen = set()
    out: list[dict] = []
    for item in items:
        kind = str(item.get("kind", ""))
        key = (
            kind,
            str(item.get("path", "")),
            str(item.get("line", "")),
            str(item.get("name", "")),
            str(item.get("paragraph_index", "")),
            str(item.get("doc_id", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _rrf_fuse(
    ranked_lists: list[tuple[str, list[tuple[str, float]]]],
    top_k: int,
    rrf_k: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for _, matches in ranked_lists:
        for rank, (doc_id, _) in enumerate(matches, start=1):
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]
