import json
import re
from pathlib import Path
from typing import Dict, List


def build_alignment_map(
    parsed_path: Path, symbol_path: Path, text_index_path: Path
) -> Dict[str, object]:
    paper = json.loads(parsed_path.read_text(encoding="utf-8"))
    symbols = _safe_load_json(symbol_path)
    text_index = _safe_load_json(text_index_path)

    symbol_entries = symbols.get("symbols", []) if isinstance(symbols, dict) else []
    text_entries = text_index.get("entries", []) if isinstance(text_index, dict) else []

    text_lookup = _build_text_lookup(text_entries)
    symbol_candidates = _build_symbol_candidates(symbol_entries, text_lookup)
    file_candidates = _build_file_candidates(text_entries)

    results = []
    for idx, paragraph in enumerate(paper.get("paragraphs", [])):
        text = paragraph.get("text", "")
        tokens = _tokenize(text)
        if not tokens:
            continue
        matches, confidence = _rank_candidates(
            tokens, symbol_candidates, file_candidates
        )
        results.append(
            {
                "paragraph_index": str(idx),
                "page": paragraph.get("page", ""),
                "text_excerpt": text[:240],
                "confidence": f"{confidence:.3f}",
                "matches": matches,
            }
        )

    return {
        "paragraph_count": str(len(paper.get("paragraphs", []))),
        "match_count": str(len(results)),
        "results": results,
    }


def write_alignment(dest_path: Path, data: dict) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def _safe_load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tokenize(text: str) -> List[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 4]
    return tokens


def _split_path_tokens(path: str) -> List[str]:
    parts = re.split(r"[\\/_\-.]", path)
    tokens: List[str] = []
    for part in parts:
        if not part:
            continue
        tokens.extend(_split_camel(part))
    return [token.lower() for token in tokens if len(token) >= 3]


def _split_camel(value: str) -> List[str]:
    return re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", value)


def _build_symbol_candidates(
    entries: List[dict], text_lookup: Dict[str, str]
) -> List[dict]:
    candidates = []
    for entry in entries:
        name = entry.get("name", "")
        path = entry.get("path", "")
        tokens = _tokenize(name) + _split_path_tokens(path)
        candidates.append(
            {
                "kind": "symbol",
                "path": path,
                "name": name,
                "type": entry.get("type", ""),
                "line": entry.get("line", ""),
                "excerpt": text_lookup.get(path, ""),
                "tokens": tokens,
            }
        )
    return candidates


def _build_file_candidates(entries: List[dict]) -> List[dict]:
    candidates = []
    for entry in entries:
        path = entry.get("path", "")
        tokens = _split_path_tokens(path)
        candidates.append(
            {
                "kind": "file",
                "path": path,
                "excerpt": entry.get("excerpt", ""),
                "tokens": tokens,
            }
        )
    return candidates


def _rank_candidates(
    tokens: List[str], symbols: List[dict], files: List[dict]
) -> tuple[List[dict], float]:
    scored: List[dict] = []
    token_set = set(tokens)
    for entry in symbols:
        score, matched = _score_tokens(token_set, entry.get("tokens", []))
        if score == 0:
            continue
        scored.append(
            {
                "kind": entry["kind"],
                "path": entry["path"],
                "name": entry.get("name", ""),
                "type": entry.get("type", ""),
                "line": entry.get("line", ""),
                "excerpt": entry.get("excerpt", "")[:200],
                "matched_tokens": matched,
                "score": str(score),
            }
        )
    for entry in files:
        score, matched = _score_tokens(token_set, entry.get("tokens", []))
        if score == 0:
            continue
        scored.append(
            {
                "kind": entry["kind"],
                "path": entry["path"],
                "excerpt": entry.get("excerpt", "")[:200],
                "matched_tokens": matched,
                "score": str(score),
            }
        )
    scored.sort(key=lambda item: int(item["score"]), reverse=True)
    top = scored[:5]
    if not tokens:
        return top, 0.0
    best = int(top[0]["score"]) if top else 0
    confidence = min(best / max(len(set(tokens)), 1), 1.0)
    return top, confidence


def _score_tokens(
    text_tokens: set, candidate_tokens: List[str]
) -> tuple[int, List[str]]:
    matched = [token for token in candidate_tokens if token in text_tokens]
    return len(matched), matched


def _build_text_lookup(entries: List[dict]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for entry in entries:
        path = entry.get("path", "")
        excerpt = entry.get("excerpt", "")
        if path:
            lookup[path] = excerpt
    return lookup
