import json
import math
import re
from pathlib import Path


def build_vector_index(
    docs: list[dict[str, str]], max_terms: int = 200
) -> dict[str, object]:
    tokenized = [(_doc_id(doc), _tokenize(doc.get("text", ""))) for doc in docs]
    df: dict[str, int] = {}
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
        tf: dict[str, int] = {}
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


def write_vector_index(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def load_vector_index(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def query_vector_index(
    index: dict[str, object], question: str, top_k: int = 5
) -> list[tuple[str, float]]:
    idf = _coerce_float_dict(index.get("idf"))
    vectors_raw = index.get("vectors")
    vectors: list[dict[str, object]] = (
        [item for item in vectors_raw if isinstance(item, dict)]
        if isinstance(vectors_raw, list)
        else []
    )
    tokens = _tokenize(question)
    if not tokens or not vectors:
        return []

    tf: dict[str, int] = {}
    for token in tokens:
        tf[token] = tf.get(token, 0) + 1
    query = {token: tf[token] * float(idf.get(token, 0.0)) for token in tf}

    scored = []
    for vec in vectors:
        weights = _coerce_float_dict(vec.get("weights"))
        score = _cosine(query, weights)
        if score > 0:
            scored.append((str(vec.get("doc_id", "")), score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def _coerce_float_dict(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
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


def _doc_id(doc: dict[str, str]) -> str:
    return doc.get("doc_id", "")


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 3]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            tokens.append(run)
        else:
            for idx in range(len(run) - 1):
                tokens.append(run[idx : idx + 2])
    return tokens
