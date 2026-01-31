import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def build_bm25_index(
    docs: List[Dict[str, str]], k1: float = 1.2, b: float = 0.75, epsilon: float = 0.25
) -> Dict[str, Any]:
    tokenized = [(_doc_id(doc), _tokenize(doc.get("text", ""))) for doc in docs]
    doc_count = len(tokenized)
    doc_len: Dict[str, int] = {}
    df: Dict[str, int] = {}
    postings: Dict[str, List[Tuple[str, int]]] = {}

    for doc_id, tokens in tokenized:
        doc_len[doc_id] = len(tokens)
        tf: Dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        for token, count in tf.items():
            df[token] = df.get(token, 0) + 1
            postings.setdefault(token, []).append((doc_id, count))

    avgdl = (sum(doc_len.values()) / doc_count) if doc_count else 0.0
    idf = {
        token: math.log((doc_count - count + 0.5) / (count + 0.5))
        for token, count in df.items()
    }

    avg_idf = 0.0
    if idf:
        avg_idf = sum(float(v) for v in idf.values()) / len(idf)
    if avg_idf > 0.0 and epsilon > 0.0:
        floor_value = epsilon * avg_idf
        for token, value in list(idf.items()):
            if float(value) < 0.0:
                idf[token] = float(floor_value)

    return {
        "schema_version": 2,
        "doc_count": doc_count,
        "avgdl": avgdl,
        "k1": float(k1),
        "b": float(b),
        "epsilon": float(epsilon),
        "idf": idf,
        "doc_len": doc_len,
        "postings": {
            k: [[doc_id, tf] for doc_id, tf in v] for k, v in postings.items()
        },
    }


def write_bm25_index(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def load_bm25_index(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def query_bm25_index(
    index: Dict[str, Any], question: str, top_k: int = 5
) -> List[Tuple[str, float]]:
    tokens = _tokenize(question)
    if not tokens:
        return []

    idf: Dict[str, float] = index.get("idf") or {}
    postings: Dict[str, list] = index.get("postings") or {}
    doc_len: Dict[str, int] = index.get("doc_len") or {}
    avgdl = float(index.get("avgdl") or 0.0)
    k1 = float(index.get("k1") or 1.2)
    b = float(index.get("b") or 0.75)
    if not postings or not doc_len or avgdl <= 0:
        return []

    scores: Dict[str, float] = {}
    for token in set(tokens):
        token_idf = float(idf.get(token, 0.0))
        if token_idf <= 0:
            continue
        for raw_item in postings.get(token, []):
            if not isinstance(raw_item, list) or len(raw_item) != 2:
                continue
            doc_id = str(raw_item[0])
            tf_i = int(raw_item[1])
            dl = int(doc_len.get(doc_id, 0) or 0)
            if dl <= 0:
                continue
            denom = tf_i + k1 * (1 - b + b * (dl / avgdl))
            if denom <= 0:
                continue
            inc = token_idf * (tf_i * (k1 + 1)) / denom
            scores[doc_id] = scores.get(doc_id, 0.0) + float(inc)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def _doc_id(doc: Dict[str, str]) -> str:
    return doc.get("doc_id", "")


def _tokenize(text: str) -> List[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 3]
    return tokens
