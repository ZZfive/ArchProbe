from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1)
    paper_url: str = Field(..., min_length=1)
    repo_url: str = Field(..., min_length=1)
    focus_points: Optional[List[str]] = None


class ProjectOut(BaseModel):
    id: str
    name: str
    paper_url: str
    repo_url: str
    focus_points: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime
    paper_hash: Optional[str] = None
    repo_hash: Optional[str] = None


class ProjectDetail(ProjectOut):
    paper_parsed_path: Optional[str] = None
    code_index_path: Optional[str] = None
    alignment_path: Optional[str] = None
    paper_vector_path: Optional[str] = None
    code_vector_path: Optional[str] = None
    paper_bm25_path: Optional[str] = None
    code_bm25_path: Optional[str] = None


class ProjectDeleteResponse(BaseModel):
    project_id: str
    deleted: bool


class IngestResponse(BaseModel):
    project_id: str
    paper_hash: str
    parsed_path: str


class CodeIndexResponse(BaseModel):
    project_id: str
    repo_hash: str
    index_path: str


class AlignmentResponse(BaseModel):
    project_id: str
    alignment_path: str
    match_count: int


class VectorIndexResponse(BaseModel):
    project_id: str
    paper_index_path: str
    code_index_path: str
    paper_bm25_path: str
    code_bm25_path: str


class AlignmentGetResponse(BaseModel):
    project_id: str
    alignment_path: Optional[str] = None
    alignment: Optional[Dict[str, object]] = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)


class AskResponse(BaseModel):
    project_id: str
    question: str
    answer: str
    confidence: float
    created_at: datetime
