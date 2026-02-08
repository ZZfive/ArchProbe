import json
from pathlib import Path
from typing import Iterable, List, Mapping

from .config import PROJECTS_DIR


def ensure_project_dirs(project_id: str) -> Path:
    project_dir = PROJECTS_DIR / project_id
    (project_dir / "paper").mkdir(parents=True, exist_ok=True)
    (project_dir / "docs").mkdir(parents=True, exist_ok=True)
    (project_dir / "code").mkdir(parents=True, exist_ok=True)
    (project_dir / "alignment").mkdir(parents=True, exist_ok=True)
    (project_dir / "qa").mkdir(parents=True, exist_ok=True)
    (project_dir / "summary").mkdir(parents=True, exist_ok=True)
    return project_dir


def write_project_meta(project_id: str, meta: Mapping[str, object]) -> None:
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


def append_qa_log(project_id: str, entry: Mapping[str, object]) -> None:
    log_path = PROJECTS_DIR / project_id / "qa" / "qa_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True))
        handle.write("\n")


def read_qa_log(project_id: str) -> List[dict[str, object]]:
    log_path = PROJECTS_DIR / project_id / "qa" / "qa_log.jsonl"
    if not log_path.exists():
        return []
    entries = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def read_project_overview(project_id: str) -> dict[str, object] | None:
    overview_path = PROJECTS_DIR / project_id / "summary" / "overview.json"
    if not overview_path.exists():
        return None
    try:
        return json.loads(overview_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_project_overview(project_id: str, content: str, version: str) -> None:
    project_dir = ensure_project_dirs(project_id)
    overview_path = project_dir / "summary" / "overview.json"
    data = {
        "content": content,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    overview_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def _read_readme_from_repo(repo_dir: Path) -> str:
    readme_names = ["README.md", "README.rst", "README.txt", "README"]
    for name in readme_names:
        readme_path = repo_dir / name
        if readme_path.exists():
            try:
                return readme_path.read_text(encoding="utf-8")[:5000]
            except (OSError, UnicodeDecodeError):
                continue
    return ""


def _read_paper_abstract(parsed_path: Path) -> str:
    if not parsed_path.exists():
        return ""
    try:
        data = json.loads(parsed_path.read_text(encoding="utf-8"))
        paragraphs = data.get("paragraphs", [])
        if paragraphs:
            first_para = paragraphs[0].get("text", "")
            return first_para[:2000]
    except (json.JSONDecodeError, OSError):
        pass
    return ""


def _get_arxiv_abstract(paper_url: str) -> str:
    import re

    match = re.search(r"arxiv\.org/abs/(\d+\.\d+)", paper_url)
    if match:
        arxiv_id = match.group(1)
        try:
            res = requests.get(
                f"https://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=10
            )
            if res.ok:
                import xml.etree.ElementTree as ET

                root = ET.fromstring(res.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                summary = root.find(".//atom:summary", ns)
                if summary is not None and summary.text:
                    return summary.text[:2000]
        except Exception:
            pass
    return ""


from datetime import datetime, timezone
import requests
