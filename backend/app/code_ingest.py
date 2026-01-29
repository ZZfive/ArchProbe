import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List


def clone_or_update_repo(repo_url: str, repo_dir: Path) -> None:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if (repo_dir / ".git").exists():
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "--all"], check=True)
        subprocess.run(
            ["git", "-C", str(repo_dir), "reset", "--hard", "origin/HEAD"], check=True
        )
        return
    subprocess.run(["git", "clone", repo_url, str(repo_dir)], check=True)


def get_repo_hash(repo_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_file_index(repo_dir: Path) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for filename in files:
            path = Path(root) / filename
            rel = path.relative_to(repo_dir)
            stat = path.stat()
            entries.append(
                {
                    "path": str(rel),
                    "size": str(stat.st_size),
                    "mtime": str(int(stat.st_mtime)),
                }
            )
    return entries


def build_symbol_index(repo_dir: Path, paths: Iterable[Path]) -> List[Dict[str, str]]:
    symbols: List[Dict[str, str]] = []
    for path in paths:
        ext = path.suffix.lower()
        if ext not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
            continue
        content = _safe_read_text(path)
        if content is None:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            match = _match_symbol(ext, line)
            if match:
                symbols.append(
                    {
                        "path": str(path.relative_to(repo_dir)),
                        "type": match["type"],
                        "name": match["name"],
                        "line": str(line_no),
                    }
                )
    return symbols


def build_text_index(repo_dir: Path, paths: Iterable[Path]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for path in paths:
        ext = path.suffix.lower()
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".pt", ".ckpt"}:
            continue
        content = _safe_read_text(path)
        if content is None:
            continue
        entries.append(
            {
                "path": str(path.relative_to(repo_dir)),
                "ext": ext,
                "excerpt": content[:2000],
            }
        )
    return entries


def _safe_read_text(path: Path) -> str | None:
    if path.stat().st_size > 1_000_000:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return None


def _match_symbol(ext: str, line: str) -> Dict[str, str] | None:
    if ext == ".py":
        match = re.match(r"^\s*(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        if match:
            return {"type": match.group(1), "name": match.group(2)}
        return None
    match = re.match(
        r"^\s*(export\s+)?(class|function)\s+([A-Za-z_][A-Za-z0-9_]*)", line
    )
    if match:
        return {"type": match.group(2), "name": match.group(3)}
    return None


def write_code_index(dest_path: Path, data: dict) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def write_symbol_index(dest_path: Path, data: dict) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def write_text_index(dest_path: Path, data: dict) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )
