import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

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
from .ingest import (
    download_pdf,
    file_sha256,
    parse_pdf_to_paragraphs,
    resolve_paper_url,
    write_parsed_json,
)
from .schemas import (
    AlignmentResponse,
    AskRequest,
    AskResponse,
    CodeIndexResponse,
    IngestResponse,
    ProjectCreate,
    ProjectDetail,
    ProjectOut,
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
    allow_origins=["http://localhost:5173"],
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
        focus_points=payload.focus_points,
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
    pdf_path = project_dir / "paper" / "paper.pdf"
    download_pdf(pdf_url, pdf_path)

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

    if not parsed_path.exists() or not symbol_path.exists():
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


@app.get("/projects/{project_id}/alignment")
def get_alignment(project_id: str) -> dict:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not row["alignment_path"]:
        return {"project_id": project_id, "alignment_path": None}
    alignment_path = Path(row["alignment_path"])
    if not alignment_path.exists():
        return {"project_id": project_id, "alignment_path": None}
    data = json.loads(alignment_path.read_text(encoding="utf-8"))
    return {"project_id": project_id, "alignment": data}


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

    try:
        response = generate_answer(payload.question, evidence)
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
        answer = f"LLM request failed: {err}"
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
    evidence = []
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
            evidence.append(
                {
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
            )
    evidence.sort(
        key=lambda item: (item.get("score", 0), item.get("paragraph_confidence", 0.0)),
        reverse=True,
    )
    return evidence[:20]
