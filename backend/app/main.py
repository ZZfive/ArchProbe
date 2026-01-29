import json
from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import PROJECTS_DIR
from .db import get_connection, init_db
from .ingest import (
    download_pdf,
    file_sha256,
    parse_pdf_to_paragraphs,
    resolve_paper_url,
    write_parsed_json,
)
from .schemas import IngestResponse, ProjectCreate, ProjectDetail, ProjectOut
from .storage import ensure_project_dirs, read_project_summary, write_project_meta


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
        **project.model_dump(), paper_parsed_path=row["paper_parsed_path"]
    )


@app.get("/projects/{project_id}/summary")
def get_summary(project_id: str) -> dict:
    summary = read_project_summary(project_id)
    return {"project_id": project_id, "summary": summary}


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
