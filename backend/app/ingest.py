import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List

import pdfplumber
import requests


ARXIV_ABS_RE = re.compile(r"arxiv\.org/(abs|pdf)/(?P<id>[^/]+)")


def resolve_paper_url(url: str) -> str:
    match = ARXIV_ABS_RE.search(url)
    if match:
        paper_id = match.group("id").replace(".pdf", "")
        return f"https://arxiv.org/pdf/{paper_id}.pdf"
    return url


def download_pdf(url: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    dest_path.write_bytes(response.content)


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_pdf_to_paragraphs(pdf_path: Path) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for paragraph in _split_paragraphs(text):
                results.append({"page": str(page_index), "text": paragraph})
    return results


def _split_paragraphs(text: str) -> List[str]:
    raw = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    return [re.sub(r"\s+", " ", chunk) for chunk in raw]


def write_parsed_json(dest_path: Path, data: dict) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )
