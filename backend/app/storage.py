import json
from pathlib import Path
from typing import Iterable, Optional

from .config import PROJECTS_DIR


def ensure_project_dirs(project_id: str) -> Path:
    project_dir = PROJECTS_DIR / project_id
    (project_dir / "paper").mkdir(parents=True, exist_ok=True)
    (project_dir / "code").mkdir(parents=True, exist_ok=True)
    (project_dir / "alignment").mkdir(parents=True, exist_ok=True)
    (project_dir / "qa").mkdir(parents=True, exist_ok=True)
    (project_dir / "summary").mkdir(parents=True, exist_ok=True)
    return project_dir


def write_project_meta(project_id: str, meta: dict) -> None:
    project_dir = ensure_project_dirs(project_id)
    meta_path = project_dir / "project.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=True, indent=2))


def read_project_summary(project_id: str) -> str:
    summary_path = PROJECTS_DIR / project_id / "summary" / "project_summary.md"
    if not summary_path.exists():
        return ""
    return summary_path.read_text(encoding="utf-8")


def append_project_summary(project_id: str, lines: Iterable[str]) -> None:
    summary_path = PROJECTS_DIR / project_id / "summary" / "project_summary.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(line.strip() for line in lines if line.strip())
    if not content:
        return
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write(content)
        handle.write("\n")
