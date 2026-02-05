import json
import heapq
import re
from pathlib import Path
from typing import Any, cast


def build_alignment_map(
    parsed_path: Path, symbol_path: Path, text_index_path: Path
) -> dict[str, object]:
    paper = json.loads(parsed_path.read_text(encoding="utf-8"))
    symbols = _safe_load_json(symbol_path)
    text_index = _safe_load_json(text_index_path)

    symbol_entries: list[dict[str, object]] = []
    if isinstance(symbols, dict):
        raw_symbols = symbols.get("symbols")
        if isinstance(raw_symbols, list):
            for item in raw_symbols:
                if isinstance(item, dict):
                    symbol_entries.append(item)

    text_entries: list[dict[str, object]] = []
    if isinstance(text_index, dict):
        raw_entries = text_index.get("entries")
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if isinstance(item, dict):
                    text_entries.append(item)

    text_lookup = _build_text_lookup(cast(list[dict[str, Any]], text_entries))
    symbol_candidates = _build_symbol_candidates(
        cast(list[dict[str, Any]], symbol_entries), text_lookup
    )
    file_candidates = _build_file_candidates(cast(list[dict[str, Any]], text_entries))

    symbol_inverted = _build_inverted_index(symbol_candidates)
    file_inverted = _build_inverted_index(file_candidates)

    results: list[dict[str, object]] = []
    raw_paragraphs = paper.get("paragraphs", []) if isinstance(paper, dict) else []
    if not isinstance(raw_paragraphs, list):
        raw_paragraphs = []
    for idx, paragraph in enumerate(raw_paragraphs):
        if not isinstance(paragraph, dict):
            continue
        text = str(paragraph.get("text", ""))
        tokens = _tokenize(text)
        if not tokens:
            continue
        matches, confidence = _rank_candidates(
            tokens,
            symbol_candidates,
            file_candidates,
            symbol_inverted,
            file_inverted,
        )
        results.append(
            {
                "paragraph_index": str(idx),
                "page": str(paragraph.get("page", "")),
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


def write_alignment(dest_path: Path, data: dict[str, object]) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
    )


def _safe_load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 4]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            tokens.append(run)
        else:
            for idx in range(len(run) - 1):
                tokens.append(run[idx : idx + 2])
    return tokens


def _split_path_tokens(path: str) -> list[str]:
    parts = re.split(r"[\\/_\-.]", path)
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        tokens.extend(_split_camel(part))
    return [token.lower() for token in tokens if len(token) >= 3]


def _split_camel(value: str) -> list[str]:
    return re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", value)


def _build_symbol_candidates(
    entries: list[dict[str, Any]], text_lookup: dict[str, str]
) -> list[dict[str, object]]:
    candidates = []
    for entry in entries:
        raw_name = entry.get("name", "")
        raw_path = entry.get("path", "")
        name = raw_name if isinstance(raw_name, str) else str(raw_name)
        path = raw_path if isinstance(raw_path, str) else str(raw_path)
        tokens = _tokenize(name) + _split_path_tokens(path)
        candidates.append(
            {
                "kind": "symbol",
                "path": path,
                "name": name,
                "type": str(entry.get("type", "")),
                "line": str(entry.get("line", "")),
                "excerpt": str(text_lookup.get(path, "")),
                "tokens": tokens,
            }
        )
    return candidates


def _build_file_candidates(entries: list[dict[str, Any]]) -> list[dict[str, object]]:
    candidates = []
    for entry in entries:
        raw_path = entry.get("path", "")
        path = raw_path if isinstance(raw_path, str) else str(raw_path)
        tokens = _split_path_tokens(path)
        candidates.append(
            {
                "kind": "file",
                "path": path,
                "excerpt": str(entry.get("excerpt", "")),
                "tokens": tokens,
            }
        )
    return candidates


def _rank_candidates(
    tokens: list[str],
    symbols: list[dict[str, Any]],
    files: list[dict[str, Any]],
    symbol_inverted: dict[str, list[int]],
    file_inverted: dict[str, list[int]],
) -> tuple[list[dict[str, object]], float]:
    token_set = set(tokens)

    scored: list[dict[str, object]] = []
    for entry in _iter_candidates(token_set, symbols, symbol_inverted):
        raw_tokens = entry.get("tokens", [])
        entry_tokens = (
            [str(token) for token in raw_tokens] if isinstance(raw_tokens, list) else []
        )
        score, matched = _score_tokens(token_set, entry_tokens)
        if score == 0:
            continue
        scored.append(
            {
                "kind": str(entry.get("kind", "")),
                "path": str(entry.get("path", "")),
                "name": str(entry.get("name", "")),
                "type": str(entry.get("type", "")),
                "line": str(entry.get("line", "")),
                "excerpt": str(entry.get("excerpt", ""))[:200],
                "matched_tokens": matched,
                "score": score,
            }
        )
    for entry in _iter_candidates(token_set, files, file_inverted):
        raw_tokens = entry.get("tokens", [])
        entry_tokens = (
            [str(token) for token in raw_tokens] if isinstance(raw_tokens, list) else []
        )
        score, matched = _score_tokens(token_set, entry_tokens)
        if score == 0:
            continue
        scored.append(
            {
                "kind": str(entry.get("kind", "")),
                "path": str(entry.get("path", "")),
                "excerpt": str(entry.get("excerpt", ""))[:200],
                "matched_tokens": matched,
                "score": score,
            }
        )

    def _score_value(item: dict[str, object]) -> int:
        raw = item.get("score", 0)
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float):
            return int(raw)
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
        return 0

    top = heapq.nlargest(5, scored, key=_score_value)
    if not tokens:
        return top, 0.0
    best = _score_value(top[0]) if top else 0
    confidence = min(best / max(len(set(tokens)), 1), 1.0)
    return top, confidence


def _score_tokens(
    text_tokens: set[str], candidate_tokens: list[str]
) -> tuple[int, list[str]]:
    matched = [token for token in candidate_tokens if token in text_tokens]
    return len(matched), matched


def _build_text_lookup(entries: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for entry in entries:
        raw_path = entry.get("path", "")
        raw_excerpt = entry.get("excerpt", "")
        path = raw_path if isinstance(raw_path, str) else str(raw_path)
        excerpt = raw_excerpt if isinstance(raw_excerpt, str) else str(raw_excerpt)
        if path:
            lookup[path] = excerpt
    return lookup


def _build_inverted_index(candidates: list[dict[str, Any]]) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for idx, item in enumerate(candidates):
        raw_tokens = item.get("tokens", [])
        tokens = (
            [str(token) for token in raw_tokens] if isinstance(raw_tokens, list) else []
        )
        for token in set(tokens):
            index.setdefault(token, []).append(idx)
    return index


def _iter_candidates(
    token_set: set[str],
    candidates: list[dict[str, Any]],
    inverted: dict[str, list[int]],
) -> list[dict[str, object]]:
    seen: set[int] = set()
    result = []
    for token in token_set:
        for idx in inverted.get(token, []):
            if idx in seen:
                continue
            seen.add(idx)
            result.append(candidates[idx])
    return result
