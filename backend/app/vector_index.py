import json
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple


def build_vector_index(
    docs: List[Dict[str, str]], max_terms: int = 200
) -> Dict[str, object]:
    tokenized = [(_doc_id(doc), _tokenize(doc.get("text", ""))) for doc in docs]
    df: Dict[str, int] = {}
    for _, tokens in tokenized:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1

    doc_count = len(tokenized)
    idf = {
        token: math.log((1 + doc_count) / (1 + count)) + 1
        for token, count in df.items()
    }

    vectors = []
    for doc, tokens in tokenized:
        tf: Dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        weights = {token: tf[token] * idf.get(token, 0.0) for token in tf}
        top_items = sorted(weights.items(), key=lambda item: item[1], reverse=True)[
            :max_terms
        ]
        vectors.append({"doc_id": doc, "weights": {k: float(v) for k, v in top_items}})

    return {
        "doc_count": doc_count,
        "idf": idf,
        "vectors": vectors,
    }


def write_vector_index(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def load_vector_index(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def query_vector_index(
    index: Dict[str, object], question: str, top_k: int = 5
) -> List[Tuple[str, float]]:
    idf = index.get("idf") or {}
    vectors = index.get("vectors") or []
    tokens = _tokenize(question)
    if not tokens or not vectors:
        return []

    tf: Dict[str, int] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    query = {token: tf[token] * float(idf.get(token, 0.0)) for token in tf}

    scored = []
    for vec in vectors:
        weights = vec.get("weights") or {}
        score = _cosine(query, weights)
        if score > 0:
            scored.append((vec.get("doc_id", ""), score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for token, value in a.items():
        norm_a += value * value
        if token in b:
            dot += value * float(b[token])
    for value in b.values():
        norm_b += float(value) * float(value)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def _doc_id(doc: Dict[str, str]) -> str:
    return doc.get("doc_id", "")


def _tokenize(text: str) -> List[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 3]
    return tokens
