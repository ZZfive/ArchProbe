import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = REPO_ROOT / "projects"
DB_PATH = REPO_ROOT / "backend" / "app.db"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "api")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


CODE_INDEX_MAX_FILES = _env_int("CODE_INDEX_MAX_FILES", 5000)
CODE_INDEX_MAX_TOTAL_BYTES = _env_int("CODE_INDEX_MAX_TOTAL_BYTES", 50_000_000)
CODE_INDEX_MAX_FILE_BYTES = _env_int("CODE_INDEX_MAX_FILE_BYTES", 1_000_000)

CODE_INDEX_IGNORE_DIRS = set(
    part.strip()
    for part in os.getenv(
        "CODE_INDEX_IGNORE_DIRS",
        ".git,node_modules,dist,build,.out,.next,.nuxt,.svelte-kit,.vite,.cache,.pytest_cache,.mypy_cache,.ruff_cache,.venv,venv,env,__pycache__",
    ).split(",")
    if part.strip()
)

CODE_INDEX_IGNORE_EXTS = set(
    part.strip().lower()
    for part in os.getenv(
        "CODE_INDEX_IGNORE_EXTS",
        ".png,.jpg,.jpeg,.gif,.webp,.mp4,.mov,.avi,.zip,.tar,.gz,.tgz,.7z,.pdf,.pt,.ckpt,.bin,.so,.dylib,.dll",
    ).split(",")
    if part.strip()
)

PAPER_MAX_PDF_BYTES = _env_int("PAPER_MAX_PDF_BYTES", 50_000_000)
PAPER_MAX_PAGES = _env_int("PAPER_MAX_PAGES", 200)
PAPER_MAX_PARAGRAPHS = _env_int("PAPER_MAX_PARAGRAPHS", 5000)
