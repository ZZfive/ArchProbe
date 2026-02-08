import json
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .config import (
    CODE_INDEX_IGNORE_DIRS,
    CODE_INDEX_IGNORE_EXTS,
    CODE_INDEX_MAX_FILE_BYTES,
    CODE_INDEX_MAX_FILES,
    CODE_INDEX_MAX_TOTAL_BYTES,
)


def clone_or_update_repo(repo_url: str, repo_dir: Path) -> None:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if (repo_dir / ".git").exists():
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "--all"], check=True)
        subprocess.run(
            ["git", "-C", str(repo_dir), "reset", "--hard", "origin/HEAD"], check=True
        )
        return
    subprocess.run(["git", "clone", "--depth=1", repo_url, str(repo_dir)], check=True)


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
    total_bytes = 0
    file_count = 0
    paths = _list_repo_files(repo_dir)
    for rel in paths:
        if _should_skip_rel_path(rel):
            continue
        abs_path = repo_dir / rel
        try:
            stat = abs_path.stat()
        except OSError:
            continue
        if not abs_path.is_file():
            continue
        total_bytes += int(stat.st_size)
        file_count += 1
        entries.append(
            {
                "path": rel,
                "size": str(stat.st_size),
                "mtime": str(int(stat.st_mtime)),
            }
        )
        if (
            file_count >= CODE_INDEX_MAX_FILES
            or total_bytes >= CODE_INDEX_MAX_TOTAL_BYTES
        ):
            break
    return entries


def _list_repo_files(repo_dir: Path) -> List[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
        raw = result.stdout
        if not raw:
            return []
        parts = raw.split(b"\x00")
        return [part.decode("utf-8", errors="ignore") for part in parts if part]
    except (OSError, subprocess.CalledProcessError):
        paths = []
        for root, dirs, files in os.walk(repo_dir):
            dirs[:] = [d for d in dirs if d != ".git"]
            for filename in files:
                path = Path(root) / filename
                try:
                    rel = path.relative_to(repo_dir)
                except ValueError:
                    continue
                paths.append(str(rel))
        return paths


def build_symbol_index(repo_dir: Path, paths: Iterable[Path]) -> List[Dict[str, str]]:
    symbols: List[Dict[str, str]] = []
    for path in paths:
        rel = str(path.relative_to(repo_dir))
        if _should_skip_rel_path(rel):
            continue
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
    chunk_lines = 160
    overlap_lines = 40
    for path in paths:
        rel = str(path.relative_to(repo_dir))
        if _should_skip_rel_path(rel):
            continue
        ext = path.suffix.lower()
        if ext in CODE_INDEX_IGNORE_EXTS:
            continue
        content = _safe_read_text(path)
        if content is None:
            continue
        lines = content.splitlines()
        if not lines:
            continue
        step = max(1, chunk_lines - overlap_lines)
        for start_idx in range(0, len(lines), step):
            end_idx = min(start_idx + chunk_lines, len(lines))
            excerpt = "\n".join(lines[start_idx:end_idx]).strip()
            if not excerpt:
                continue
            entries.append(
                {
                    "path": rel,
                    "ext": ext,
                    "start_line": str(start_idx + 1),
                    "end_line": str(end_idx),
                    "excerpt": excerpt,
                }
            )
            if end_idx >= len(lines):
                break
    return entries


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > CODE_INDEX_MAX_FILE_BYTES:
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
        match = re.match(
            r"^\s*(class|(?:async\s+)?def)\s+([A-Za-z_][A-Za-z0-9_]*)", line
        )
        if match:
            symbol_type = (
                "def" if match.group(1) in {"async def", "def"} else match.group(1)
            )
            return {"type": symbol_type, "name": match.group(2)}
        return None
    match = re.match(
        r"^\s*(export\s+)?(?:async\s+)?(class|function)\s+([A-Za-z_][A-Za-z0-9_]*)",
        line,
    )
    if match:
        return {"type": match.group(2), "name": match.group(3)}
    match = re.match(
        r"^\s*export\s+default\s+function\s+([A-Za-z_][A-Za-z0-9_]*)", line
    )
    if match:
        return {"type": "function", "name": match.group(1)}
    return None


def write_code_index(dest_path: Path, data: Dict[str, object]) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def write_symbol_index(dest_path: Path, data: Dict[str, object]) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def write_text_index(dest_path: Path, data: Dict[str, object]) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def _should_skip_rel_path(rel_path: str) -> bool:
    if not rel_path:
        return True
    parts = rel_path.split("/")
    for part in parts[:-1]:
        if part in CODE_INDEX_IGNORE_DIRS:
            return True
    ext = Path(rel_path).suffix.lower()
    if ext and ext in CODE_INDEX_IGNORE_EXTS:
        return True
    return False
