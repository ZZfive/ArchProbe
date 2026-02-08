import hashlib
import html
import json
import re
from pathlib import Path
from typing import Dict, List

import pdfplumber
import requests

from .config import PAPER_MAX_PAGES, PAPER_MAX_PARAGRAPHS, PAPER_MAX_PDF_BYTES


ARXIV_ABS_RE = re.compile(r"arxiv\.org/(abs|pdf)/(?P<id>[^/]+)")


def resolve_paper_url(url: str) -> str:
    match = ARXIV_ABS_RE.search(url)
    if match:
        paper_id = match.group("id").replace(".pdf", "")
        return f"https://arxiv.org/pdf/{paper_id}.pdf"
    return url


def download_pdf(url: str, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=60, stream=True)
    response.raise_for_status()
    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit():
        if int(content_length) > PAPER_MAX_PDF_BYTES:
            raise ValueError(
                f"PDF too large: {content_length} bytes (limit {PAPER_MAX_PDF_BYTES})"
            )
    written = 0
    try:
        with dest_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                written += len(chunk)
                if written > PAPER_MAX_PDF_BYTES:
                    raise ValueError(
                        f"PDF too large while downloading: {written} bytes (limit {PAPER_MAX_PDF_BYTES})"
                    )
                handle.write(chunk)
    except Exception:
        try:
            dest_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


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
            if page_index > PAPER_MAX_PAGES:
                break
            text = page.extract_text() or ""
            for paragraph in _split_paragraphs(text):
                results.append({"page": str(page_index), "text": paragraph})
                if len(results) >= PAPER_MAX_PARAGRAPHS:
                    return results
    return results


def _split_paragraphs(text: str) -> List[str]:
    raw = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    return [re.sub(r"\s+", " ", chunk) for chunk in raw]


def fetch_webpage_paragraphs(url: str, max_paragraphs: int = 200) -> List[str]:
    res = requests.get(url, timeout=30)
    res.raise_for_status()
    content_type = str(res.headers.get("Content-Type", "")).lower()
    text = res.text

    if "html" in content_type or "<html" in text.lower():
        text = _html_to_text(text)

    paragraphs = _split_paragraphs(text)
    if len(paragraphs) > max_paragraphs:
        return paragraphs[:max_paragraphs]
    return paragraphs


def _html_to_text(raw_html: str) -> str:
    cleaned = re.sub(
        r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>",
        " ",
        raw_html,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"</(p|div|section|article|li|h[1-6])>", "\n\n", cleaned, flags=re.IGNORECASE
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def write_parsed_json(dest_path: Path, data: Dict[str, object]) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )
