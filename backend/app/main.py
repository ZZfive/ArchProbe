import json
import heapq
import itertools
import re
import shutil
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, List, cast
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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
    CodeFileResponse,
    CodeSnippetResponse,
    IngestResponse,
    OverviewResponse,
    ProjectCreate,
    ProjectDeleteResponse,
    ProjectDetail,
    ProjectOut,
    VectorIndexResponse,
)
from .llm import (
    LLMError,
    generate_answer,
    generate_answer_stream,
    generate_overview_full_stream,
    generate_overview_stream,
)
from .storage import (
    append_project_summary,
    append_qa_log,
    ensure_project_dirs,
    read_project_overview,
    read_project_summary,
    read_qa_log,
    write_project_overview,
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
        paper_vector_path=row["paper_vector_path"],
        code_vector_path=row["code_vector_path"],
        paper_bm25_path=row["paper_bm25_path"],
        code_bm25_path=row["code_bm25_path"],
    )


@app.delete("/projects/{project_id}", response_model=ProjectDeleteResponse)
def delete_project(project_id: str) -> ProjectDeleteResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # Delete DB row but only commit after filesystem cleanup succeeds.
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

        project_dir = PROJECTS_DIR / project_id
        try:
            if project_dir.exists():
                shutil.rmtree(project_dir)
        except OSError as err:
            conn.rollback()
            raise HTTPException(
                status_code=500, detail=f"Failed to delete project files: {err}"
            )

        conn.commit()
    finally:
        conn.close()

    return ProjectDeleteResponse(project_id=project_id, deleted=True)


@app.get("/projects/{project_id}/summary")
def get_summary(project_id: str) -> dict[str, object]:
    summary = read_project_summary(project_id)
    return {"project_id": project_id, "summary": summary}


@app.get("/projects/{project_id}/qa")
def get_qa_log(project_id: str) -> dict[str, object]:
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

    try:
        paper_hash = file_sha256(pdf_path)
    except (OSError, IOError) as err:
        raise HTTPException(
            status_code=500, detail=f"Failed to read downloaded PDF: {err}"
        )

    try:
        paragraphs = parse_pdf_to_paragraphs(pdf_path)
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Failed to parse PDF: {err}")

    try:
        write_parsed_json(
            parsed_path,
            {
                "source_url": pdf_url,
                "paper_hash": paper_hash,
                "paragraphs": paragraphs,
            },
        )
    except (OSError, IOError) as err:
        raise HTTPException(
            status_code=500, detail=f"Failed to save parsed data: {err}"
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

    existing_alignment_path = row["alignment_path"]
    if existing_alignment_path:
        existing_path = Path(existing_alignment_path)
        if existing_path.exists():
            try:
                data = json.loads(existing_path.read_text(encoding="utf-8"))
                raw_count = data.get("match_count", "0")
            except json.JSONDecodeError:
                raw_count = "0"
            if isinstance(raw_count, int):
                match_count = raw_count
            elif isinstance(raw_count, str) and raw_count.isdigit():
                match_count = int(raw_count)
            else:
                match_count = 0
            return AlignmentResponse(
                project_id=project_id,
                alignment_path=str(existing_path),
                match_count=match_count,
            )

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

    paper_index_path = project_dir / "paper" / "vector_index.json"
    code_index_path = project_dir / "code" / "vector_index.json"
    paper_bm25_path = project_dir / "paper" / "bm25_index.json"
    code_bm25_path = project_dir / "code" / "bm25_index.json"
    if (
        paper_index_path.exists()
        and code_index_path.exists()
        and paper_bm25_path.exists()
        and code_bm25_path.exists()
    ):
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE projects
                SET paper_vector_path = ?, code_vector_path = ?, paper_bm25_path = ?, code_bm25_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(paper_index_path),
                    str(code_index_path),
                    str(paper_bm25_path),
                    str(code_bm25_path),
                    now,
                    project_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return VectorIndexResponse(
            project_id=project_id,
            paper_index_path=str(paper_index_path),
            code_index_path=str(code_index_path),
            paper_bm25_path=str(paper_bm25_path),
            code_bm25_path=str(code_bm25_path),
        )

    paper_index = build_vector_index(paper_docs)
    code_index = build_vector_index(code_docs)
    write_vector_index(paper_index_path, paper_index)
    write_vector_index(code_index_path, code_index)

    paper_bm25 = build_bm25_index(paper_docs)
    code_bm25 = build_bm25_index(code_docs)
    write_bm25_index(paper_bm25_path, paper_bm25)
    write_bm25_index(code_bm25_path, code_bm25)

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE projects
            SET paper_vector_path = ?, code_vector_path = ?, paper_bm25_path = ?, code_bm25_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(paper_index_path),
                str(code_index_path),
                str(paper_bm25_path),
                str(code_bm25_path),
                now,
                project_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

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
    project_dir = ensure_project_dirs(project_id)
    route, evidence, evidence_mix, insufficient_evidence = _build_routed_evidence(
        project_dir=project_dir,
        question=payload.question,
        focus_points=focus_points,
        alignment_path=str(row["alignment_path"] or ""),
    )
    llm_question = _with_llm_context(
        payload.question, route, evidence_mix, insufficient_evidence
    )

    try:
        response = generate_answer(
            llm_question,
            evidence,
            focus_points=focus_points or None,
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
        "route": route,
        "evidence_mix": evidence_mix,
        "insufficient_evidence": insufficient_evidence,
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


@app.post("/projects/{project_id}/ask-stream")
def ask_project_stream(project_id: str, payload: AskRequest) -> StreamingResponse:
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

    project_dir = ensure_project_dirs(project_id)
    route, evidence, evidence_mix, insufficient_evidence = _build_routed_evidence(
        project_dir=project_dir,
        question=payload.question,
        focus_points=focus_points,
        alignment_path=str(row["alignment_path"] or ""),
    )
    llm_question = _with_llm_context(
        payload.question, route, evidence_mix, insufficient_evidence
    )

    def stream_generator():
        answer_parts = []
        try:
            for chunk in generate_answer_stream(
                llm_question,
                evidence,
                focus_points=focus_points or None,
            ):
                answer_parts.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

            answer = "".join(answer_parts)
            now = datetime.now(timezone.utc).isoformat()
            code_refs = _extract_code_refs_for_question(
                evidence, question=payload.question, project_dir=project_dir
            )
            entry = {
                "question": payload.question,
                "answer": answer,
                "evidence": evidence,
                "route": route,
                "evidence_mix": evidence_mix,
                "insufficient_evidence": insufficient_evidence,
                "code_refs": code_refs,
                "confidence": 0.6,
                "created_at": now,
            }
            append_qa_log(project_id, entry)
            append_project_summary(
                project_id, [f"Q: {payload.question}", f"A: {answer}", "---"]
            )
            yield f"data: {json.dumps({'done': True, 'answer': answer, 'code_refs': code_refs, 'route': route, 'evidence_mix': evidence_mix, 'insufficient_evidence': insufficient_evidence}, ensure_ascii=False)}\n\n"
        except LLMError as err:
            yield f"data: {json.dumps({'error': str(err)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _route_question(question: str) -> str:
    q = question.strip().lower()
    if not q:
        return "fallback"

    code_markers = [
        "code",
        "repo",
        "repository",
        "file",
        "files",
        "filepath",
        "path",
        "function",
        "class",
        "module",
        "import",
        "endpoint",
        "api",
        "fastapi",
        "frontend",
        "backend",
        "typescript",
        "react",
        "implementation",
        "where is",
        "which file",
    ]
    paper_markers = [
        "paper",
        "section",
        "figure",
        "table",
        "equation",
        "theorem",
        "lemma",
        "proof",
        "appendix",
        "abstract",
        "introduction",
        "method",
        "experiment",
        "results",
        "dataset",
        "hyperparameter",
        "ablation",
        "arxiv",
    ]

    code_score = 0
    paper_score = 0
    for m in code_markers:
        if m in q:
            code_score += 1
    for m in paper_markers:
        if m in q:
            paper_score += 1

    # Code-ish syntax indicators.
    if "/" in question or "::" in question or "(" in question or "`" in question:
        code_score += 1
    if re.search(r"\.(py|ts|tsx|js|jsx|md|json|yaml|yml|toml)\b", q):
        code_score += 2

    if paper_score >= 2 and code_score == 0:
        return "paper_only"
    if code_score >= 2 and paper_score == 0:
        return "code_only"
    if paper_score > 0 and code_score > 0:
        return "hybrid"
    return "fallback"


def _tokenize_query(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [tok.lower() for tok in raw if len(tok) >= 3]
    # Preserve some file-ish suffix tokens (ts/py) via regex above.
    return tokens


def _with_llm_context(
    question: str,
    route: str,
    evidence_mix: dict[str, object],
    insufficient_evidence: bool,
) -> str:
    mix_str = ""
    paper_pct = evidence_mix.get("paper_pct")
    code_pct = evidence_mix.get("code_pct")
    if paper_pct is not None and code_pct is not None:
        mix_str = f"paper={paper_pct}% code={code_pct}%"
    return (
        question
        + "\n\nContext:\n"
        + f"- route={route}\n"
        + (f"- evidence_mix={mix_str}\n" if mix_str else "")
        + f"- insufficient_evidence={str(bool(insufficient_evidence)).lower()}"
    )


def _evidence_text(item: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("path", "name", "doc_id", "excerpt", "text_excerpt"):
        val = item.get(key)
        if val:
            parts.append(str(val))
    return "\n".join(parts)


def _filter_evidence_by_relevance(
    evidence: list[dict[str, object]], query_text: str
) -> list[dict[str, object]]:
    tokens = set(_tokenize_query(query_text))
    if not tokens:
        return evidence

    def _keep(item: dict[str, object]) -> bool:
        text = _evidence_text(item).lower()
        if not text:
            return False
        overlap = 0
        for tok in tokens:
            if tok in text:
                overlap += 1
        if len(tokens) <= 3:
            return overlap >= 1
        ratio = overlap / max(len(tokens), 1)
        return overlap >= 2 or ratio >= 0.12

    kept = [ev for ev in evidence if _keep(ev)]
    # Avoid returning empty evidence solely due to filtering.
    return kept if kept else evidence[:3]


def _compute_evidence_mix(evidence: list[dict[str, object]]) -> dict[str, object]:
    paper = 0
    code = 0
    for item in evidence:
        kind = str(item.get("kind", ""))
        if kind.startswith("paper"):
            paper += 1
        elif kind.startswith("code") or kind in {"symbol", "file"}:
            code += 1
        else:
            # Default unknown evidence kinds to code-ish.
            code += 1
    total = paper + code
    paper_pct = int(round((paper / total) * 100)) if total else 0
    code_pct = 100 - paper_pct if total else 0
    return {
        "paper_count": paper,
        "code_count": code,
        "total": total,
        "paper_pct": paper_pct,
        "code_pct": code_pct,
    }


def _load_paper_paragraphs(project_dir: Path) -> list[dict[str, object]]:
    parsed_path = project_dir / "paper" / "parsed.json"
    if not parsed_path.exists():
        return []
    try:
        paper_data = json.loads(parsed_path.read_text(encoding="utf-8"))
        raw_paragraphs = paper_data.get("paragraphs", [])
        if isinstance(raw_paragraphs, list):
            return raw_paragraphs
    except (OSError, json.JSONDecodeError):
        return []
    return []


def _load_code_excerpts(project_dir: Path) -> dict[str, str]:
    text_index_path = project_dir / "code" / "text_index.json"
    if not text_index_path.exists():
        return {}
    out: dict[str, str] = {}
    try:
        code_data = json.loads(text_index_path.read_text(encoding="utf-8"))
        for entry in code_data.get("entries", []):
            path = entry.get("path")
            excerpt = entry.get("excerpt")
            if path and excerpt and path not in out:
                out[str(path)] = str(excerpt)
    except (OSError, json.JSONDecodeError):
        return {}
    return out


def _build_routed_evidence(
    project_dir: Path,
    question: str,
    focus_points: list[str],
    alignment_path: str,
) -> tuple[str, list[dict[str, object]], dict[str, object], bool]:
    route = _route_question(question)

    query_text = question
    if focus_points:
        query_text = query_text + "\n\nFocus points: " + ", ".join(focus_points)

    paper_paragraphs = _load_paper_paragraphs(project_dir)
    code_excerpts = _load_code_excerpts(project_dir)

    want_paper = route in {"paper_only", "hybrid", "fallback"}
    want_code = route in {"code_only", "hybrid", "fallback"}

    # Alignment evidence is treated as auxiliary signal (only for hybrid).
    alignment_evidence: list[dict[str, object]] = []
    if route == "hybrid" and alignment_path:
        alignment_file = Path(alignment_path)
        if alignment_file.exists():
            try:
                alignment = json.loads(alignment_file.read_text(encoding="utf-8"))
                alignment_evidence = _collect_evidence(alignment)
            except (OSError, json.JSONDecodeError):
                alignment_evidence = []

    evidence: list[dict[str, object]] = []

    if want_paper:
        paper_vector_path = project_dir / "paper" / "vector_index.json"
        paper_vec_matches: list[tuple[str, float]] = []
        if paper_vector_path.exists():
            paper_index = load_vector_index(paper_vector_path)
            paper_vec_matches = query_vector_index(paper_index, query_text, top_k=5)

        paper_bm25_path = project_dir / "paper" / "bm25_index.json"
        paper_bm25_matches: list[tuple[str, float]] = []
        if paper_bm25_path.exists():
            paper_bm25 = load_bm25_index(paper_bm25_path)
            paper_bm25_matches = query_bm25_index(paper_bm25, query_text, top_k=5)

        for doc_id, score in _rrf_fuse(
            [("tfidf", paper_vec_matches), ("bm25", paper_bm25_matches)],
            top_k=3,
        ):
            ev: dict[str, object] = {}
            ev["kind"] = "paper_hybrid"
            ev["doc_id"] = doc_id
            ev["score"] = score
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

    if want_code:
        code_vector_path = project_dir / "code" / "vector_index.json"
        code_vec_matches: list[tuple[str, float]] = []
        if code_vector_path.exists():
            code_index = load_vector_index(code_vector_path)
            code_vec_matches = query_vector_index(code_index, query_text, top_k=5)

        code_bm25_path = project_dir / "code" / "bm25_index.json"
        code_bm25_matches: list[tuple[str, float]] = []
        if code_bm25_path.exists():
            code_bm25 = load_bm25_index(code_bm25_path)
            code_bm25_matches = query_bm25_index(code_bm25, query_text, top_k=5)

        for doc_id, score in _rrf_fuse(
            [("tfidf", code_vec_matches), ("bm25", code_bm25_matches)],
            top_k=3,
        ):
            ev = {
                "kind": "code_hybrid",
                "doc_id": doc_id,
                "score": score,
            }
            if isinstance(doc_id, str) and doc_id.startswith("code:"):
                rel = doc_id.split(":", 1)[1]
                if rel:
                    ev["path"] = rel
                    ev["excerpt"] = code_excerpts.get(rel, "")[:240]
            evidence.append(ev)

    # Cap alignment contribution (aux signal): at most 2 items.
    if alignment_evidence:
        evidence.extend(alignment_evidence[:2])

    evidence = _dedup_evidence(evidence)
    evidence = _filter_evidence_by_relevance(evidence, query_text)
    evidence_mix = _compute_evidence_mix(evidence)
    insufficient = bool(not evidence)
    return route, evidence, evidence_mix, insufficient

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _collect_evidence(alignment: dict[str, object]) -> list[dict[str, object]]:
    limit = 20
    # heap items are compared lexicographically; include a monotonic counter so ties
    # on (score, paragraph_confidence) never fall back to comparing dict entries.
    heap: list[tuple[tuple[int, float], int]] = []
    entries_by_id: dict[int, dict[str, object]] = {}
    counter = itertools.count()
    raw_results = alignment.get("results", [])
    if not isinstance(raw_results, list):
        return []

    for item in raw_results:
        if not isinstance(item, dict):
            continue
        raw_matches = item.get("matches", [])
        if not isinstance(raw_matches, list):
            continue
        for match in raw_matches:
            if not isinstance(match, dict):
                continue
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
            entry: dict[str, object] = {
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
            entry_id = next(counter)
            entries_by_id[entry_id] = entry
            if len(heap) < limit:
                heapq.heappush(heap, (key, entry_id))
            else:
                popped_key, popped_id = heapq.heappushpop(heap, (key, entry_id))
                if popped_id != entry_id:
                    entries_by_id.pop(popped_id, None)
                else:
                    entries_by_id.pop(entry_id, None)

    top: list[dict[str, object]] = []
    for _, entry_id in sorted(heap, key=lambda pair: pair[0], reverse=True):
        try:
            top.append(entries_by_id[entry_id])
        except KeyError:
            continue
    return top


def _dedup_evidence(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen = set()
    out: list[dict[str, object]] = []
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


def _extract_code_refs(evidence: list[dict[str, object]]) -> list[dict[str, object]]:
    return _extract_code_refs_for_question(evidence, question="", project_dir=None)


def _extract_code_refs_for_question(
    evidence: list[dict[str, object]],
    question: str,
    project_dir: Path | None,
    target_refs: int = 3,
    max_refs: int = 5,
) -> list[dict[str, object]]:
    def _coerce_line(value: object) -> int:
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            parsed = int(value)
            return parsed if parsed > 0 else 1
        return 1

    def _make_ref(path: str, line: int, name: str) -> dict[str, object]:
        line_num = line if line > 0 else 1
        return {
            "path": path,
            "line": line_num,
            "name": name,
            "start_line": max(1, line_num - 5),
            "end_line": line_num + 15,
        }

    def _make_file_ref(path: str) -> dict[str, object]:
        return {
            "path": path,
            "line": 1,
            "name": "",
            "start_line": 1,
            "end_line": 50,
        }

    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "our",
        "should",
        "tell",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "why",
        "with",
        "would",
        "you",
    }

    def _split_identifier(text: str) -> list[str]:
        if not text:
            return []
        # Split underscores/dashes, then split camelCase/PascalCase.
        parts: list[str] = []
        for chunk in re.split(r"[^A-Za-z0-9]+", text):
            if not chunk:
                continue
            parts.extend(
                [p for p in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", chunk) if p]
            )
        return parts

    def _tokenize_question(text: str) -> set[str]:
        out: set[str] = set()
        # Preserve original casing so we can split camelCase/PascalCase.
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text):
            for part in _split_identifier(token):
                low = part.lower()
                if low in stopwords:
                    continue
                if len(low) < 2:
                    continue
                out.add(low)
        return out

    def _path_tokens(path: str) -> set[str]:
        out: set[str] = set()
        for part in path.replace("\\", "/").split("/"):
            for tok in _split_identifier(part):
                low = tok.lower()
                if len(low) >= 2 and low not in stopwords:
                    out.add(low)
        return out

    def _name_tokens(name: str) -> set[str]:
        out: set[str] = set()
        for tok in _split_identifier(name):
            low = tok.lower()
            if len(low) >= 2 and low not in stopwords:
                out.add(low)
        return out

    def _score_symbol(
        sym: dict[str, object], query_tokens: set[str], boost_paths: set[str]
    ) -> float:
        path = str(sym.get("path", ""))
        name = str(sym.get("name", ""))
        if not path or not name:
            return 0.0
        name_toks = _name_tokens(name)
        path_toks = _path_tokens(path)
        if not name_toks and not path_toks:
            return 0.0
        overlap_name = len(query_tokens & name_toks)
        overlap_path = len(query_tokens & path_toks)
        score = float(overlap_name * 2 + overlap_path)
        if path in boost_paths:
            score += 3.0
        return score

    refs: list[dict[str, object]] = []
    seen: set[tuple[str, int, str]] = set()

    evidence_paths: set[str] = set()
    for item in evidence:
        kind = str(item.get("kind", ""))
        path = str(item.get("path", ""))
        if not path:
            continue
        if kind in ("symbol", "code_hybrid"):
            evidence_paths.add(path)

    # 1) Prefer existing symbol evidence (path+line).
    for item in evidence:
        if len(refs) >= max_refs:
            break
        kind = str(item.get("kind", ""))
        if kind != "symbol":
            continue
        path = str(item.get("path", ""))
        if not path:
            continue
        line_num = _coerce_line(item.get("line"))
        name = str(item.get("name", ""))
        key = (path, line_num, name)
        if key in seen:
            continue
        seen.add(key)
        refs.append(_make_ref(path, line_num, name))

    # 2) If we still need refs, score symbols.json against question tokens.
    query_tokens = _tokenize_question(question)
    scored_added = 0
    if len(refs) < target_refs and project_dir is not None and query_tokens:
        symbols_path = project_dir / "code" / "symbols.json"
        symbols: list[dict[str, object]] = []
        try:
            if symbols_path.exists():
                data = json.loads(symbols_path.read_text(encoding="utf-8"))
                raw_symbols = data.get("symbols", [])
                if isinstance(raw_symbols, list):
                    for item in raw_symbols:
                        if isinstance(item, dict):
                            symbols.append(item)
        except (OSError, json.JSONDecodeError):
            symbols = []

        def _rank(
            candidates: list[dict[str, object]],
        ) -> list[tuple[float, dict[str, object]]]:
            ranked: list[tuple[float, dict[str, object]]] = []
            for sym in candidates:
                score = _score_symbol(sym, query_tokens, evidence_paths)
                if score <= 0:
                    continue
                ranked.append((score, sym))
            ranked.sort(key=lambda pair: pair[0], reverse=True)
            return ranked

        ranked = []
        if evidence_paths:
            ranked = _rank(
                [s for s in symbols if str(s.get("path", "")) in evidence_paths]
            )
        if not ranked:
            ranked = _rank(symbols)

        for _, sym in ranked:
            if len(refs) >= max_refs or len(refs) >= target_refs:
                break
            path = str(sym.get("path", ""))
            if not path:
                continue
            line_num = _coerce_line(sym.get("line"))
            name = str(sym.get("name", ""))
            key = (path, line_num, name)
            if key in seen:
                continue
            seen.add(key)
            refs.append(_make_ref(path, line_num, name))
            scored_added += 1

    # 3) If symbol scoring yields nothing, fall back to file-level refs (line=1).
    if len(refs) < target_refs and scored_added == 0 and evidence_paths:
        for path in sorted(evidence_paths):
            if len(refs) >= max_refs or len(refs) >= target_refs:
                break
            key = (path, 1, "")
            if key in seen:
                continue
            seen.add(key)
            refs.append(_make_file_ref(path))

    return refs[:max_refs]


def _parse_focus_points(raw_focus: str | None) -> list[str]:
    if not raw_focus:
        return []
    try:
        parsed = json.loads(raw_focus)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        return []
    return []


def _detect_language_from_path(rel_path: str) -> str:
    suffix = Path(rel_path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".md": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cu": "cuda",
        ".sh": "bash",
    }.get(suffix, "text")


def _read_repo_text_file(repo_dir: Path, rel_path: str) -> str:
    repo_root = repo_dir.resolve()
    abs_path = (repo_dir / rel_path).resolve()
    try:
        abs_path.relative_to(repo_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not abs_path.exists() or not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        return abs_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return abs_path.read_bytes().decode("utf-8", errors="replace")
        except OSError as err:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {err}")
    except OSError as err:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {err}")


def _read_readme(repo_dir: Path) -> str:
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        readme_path = repo_dir / name
        if not readme_path.exists() or not readme_path.is_file():
            continue
        try:
            return readme_path.read_text(encoding="utf-8")[:5000]
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def _extract_arxiv_id(paper_url: str) -> str:
    try:
        parsed = urlparse(paper_url)
    except Exception:
        return ""

    host = (parsed.netloc or "").lower()
    if host not in {"arxiv.org", "www.arxiv.org"}:
        return ""

    path = (parsed.path or "").strip()
    arxiv_id = ""
    if "/abs/" in path:
        arxiv_id = path.split("/abs/", 1)[1]
    elif "/pdf/" in path:
        arxiv_id = path.split("/pdf/", 1)[1]
        if arxiv_id.endswith(".pdf"):
            arxiv_id = arxiv_id[: -len(".pdf")]

    arxiv_id = arxiv_id.strip("/")
    if not arxiv_id:
        return ""

    # Permit both new-style (2101.00001v2) and old-style (cs/9901001) IDs.
    if not re.match(r"^[A-Za-z0-9._/-]+(v\d+)?$", arxiv_id):
        return ""
    return arxiv_id


def _fetch_arxiv_abstract(paper_url: str) -> str:
    arxiv_id = _extract_arxiv_id(paper_url)
    if not arxiv_id:
        return ""

    try:
        res = requests.get(
            "https://export.arxiv.org/api/query",
            params={"id_list": arxiv_id},
            timeout=10,
        )
        res.raise_for_status()
    except requests.RequestException:
        return ""

    try:
        root = ET.fromstring(res.text)
    except ET.ParseError:
        return ""

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return ""
    summary = entry.findtext("atom:summary", default="", namespaces=ns)
    abstract = " ".join(str(summary).split()).strip()
    return abstract[:2000]


def _normalize_lang(raw_lang: str | None) -> str:
    lang = (raw_lang or "").strip().lower()
    if lang == "en":
        return "en"
    if lang == "zh":
        return "zh"
    return "zh"


@app.get("/projects/{project_id}/overview", response_model=OverviewResponse)
def get_project_overview(project_id: str) -> OverviewResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    data = read_project_overview(project_id)
    if not data:
        raise HTTPException(status_code=404, detail="Overview not found")

    raw_generated_at = data.get("generated_at")
    try:
        generated_at = datetime.fromisoformat(str(raw_generated_at))
    except (TypeError, ValueError):
        generated_at = datetime.now(timezone.utc)

    return OverviewResponse(
        project_id=project_id,
        content=str(data.get("content", "")),
        version=str(data.get("version", "")),
        generated_at=generated_at,
    )


@app.post("/projects/{project_id}/overview/generate-quick")
def generate_project_overview_quick(
    project_id: str, lang: str | None = Query(None)
) -> StreamingResponse:
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

    parsed_path = project_dir / "paper" / "parsed.json"
    paper_abstract = ""
    paper_url = str(row["paper_url"])
    if _extract_arxiv_id(paper_url):
        paper_abstract = _fetch_arxiv_abstract(paper_url)
    if not paper_abstract and parsed_path.exists():
        try:
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            paragraphs = parsed.get("paragraphs", [])
            if isinstance(paragraphs, list) and paragraphs:
                paper_abstract = str(paragraphs[0].get("text", ""))[:2000]
        except (json.JSONDecodeError, OSError):
            paper_abstract = ""

    readme_content = _read_readme(repo_dir) if repo_dir.exists() else ""
    focus_points = _parse_focus_points(row["focus_points"])
    overview_lang = _normalize_lang(lang)

    def stream_generator():
        parts: list[str] = []
        try:
            for chunk in generate_overview_stream(
                project_name=str(row["name"]),
                paper_url=str(row["paper_url"]),
                repo_url=str(row["repo_url"]),
                readme_content=readme_content,
                paper_abstract=paper_abstract,
                focus_points=focus_points or None,
                lang=overview_lang,
            ):
                parts.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

            content = "".join(parts)
            write_project_overview(project_id, content, version="quick")
            yield f"data: {json.dumps({'done': True, 'content': content}, ensure_ascii=False)}\n\n"
        except LLMError as err:
            yield f"data: {json.dumps({'error': str(err)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/projects/{project_id}/overview/generate-full")
def generate_project_overview_full(
    project_id: str, lang: str | None = Query(None)
) -> StreamingResponse:
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
    parsed_path = project_dir / "paper" / "parsed.json"
    symbols_path = project_dir / "code" / "symbols.json"
    if not repo_dir.exists() or not parsed_path.exists() or not symbols_path.exists():
        raise HTTPException(
            status_code=400, detail="Run paper ingest and code index first"
        )

    readme_content = _read_readme(repo_dir)
    focus_points = _parse_focus_points(row["focus_points"])
    overview_lang = _normalize_lang(lang)

    paper_paragraphs: list[str] = []
    try:
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        raw_paragraphs = parsed.get("paragraphs", [])
        if isinstance(raw_paragraphs, list):
            for item in raw_paragraphs:
                if isinstance(item, dict) and str(item.get("text", "")).strip():
                    paper_paragraphs.append(str(item.get("text", "")))
    except (json.JSONDecodeError, OSError):
        paper_paragraphs = []

    code_symbols: list[dict[str, str]] = []
    try:
        sym_data = json.loads(symbols_path.read_text(encoding="utf-8"))
        raw_symbols = sym_data.get("symbols", [])
        if isinstance(raw_symbols, list):
            for item in raw_symbols:
                if isinstance(item, dict):
                    path = item.get("path")
                    typ = item.get("type")
                    name = item.get("name")
                    line = item.get("line")
                    if path and typ and name and line:
                        code_symbols.append(
                            {
                                "path": str(path),
                                "type": str(typ),
                                "name": str(name),
                                "line": str(line),
                            }
                        )
    except (json.JSONDecodeError, OSError):
        code_symbols = []

    def stream_generator():
        parts: list[str] = []
        try:
            for chunk in generate_overview_full_stream(
                project_name=str(row["name"]),
                paper_url=str(row["paper_url"]),
                repo_url=str(row["repo_url"]),
                readme_content=readme_content,
                paper_paragraphs=paper_paragraphs,
                code_symbols=code_symbols,
                focus_points=focus_points or None,
                lang=overview_lang,
            ):
                parts.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"

            content = "".join(parts)
            write_project_overview(project_id, content, version="full")
            yield f"data: {json.dumps({'done': True, 'content': content}, ensure_ascii=False)}\n\n"
        except LLMError as err:
            yield f"data: {json.dumps({'error': str(err)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/projects/{project_id}/code/file", response_model=CodeFileResponse)
def get_code_file(
    project_id: str, path: str = Query(..., min_length=1)
) -> CodeFileResponse:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    repo_dir = ensure_project_dirs(project_id) / "code" / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=400, detail="Run code index first")

    content = _read_repo_text_file(repo_dir, path)
    return CodeFileResponse(
        project_id=project_id,
        path=path,
        content=content,
        language=_detect_language_from_path(path),
    )


@app.get("/projects/{project_id}/code/snippet", response_model=CodeSnippetResponse)
def get_code_snippet(
    project_id: str,
    path: str = Query(..., min_length=1),
    start_line: int = Query(..., ge=1),
    end_line: int = Query(..., ge=1),
) -> CodeSnippetResponse:
    if end_line < start_line:
        raise HTTPException(status_code=400, detail="end_line must be >= start_line")

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")

    repo_dir = ensure_project_dirs(project_id) / "code" / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=400, detail="Run code index first")

    full = _read_repo_text_file(repo_dir, path)
    lines = full.splitlines()

    total_lines = len(lines)
    if start_line > total_lines:
        raise HTTPException(status_code=400, detail="start_line out of bounds")
    if end_line > total_lines:
        end_line = total_lines

    content = "\n".join(lines[start_line - 1 : end_line])
    return CodeSnippetResponse(
        project_id=project_id,
        path=path,
        content=content,
        language=_detect_language_from_path(path),
        start_line=start_line,
        end_line=end_line,
    )
