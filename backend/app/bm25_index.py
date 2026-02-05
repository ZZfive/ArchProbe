import json
import math
import re
from pathlib import Path


def build_bm25_index(
    docs: list[dict[str, str]],
    k1: float = 1.2,
    b: float = 0.75,
    epsilon: float = 0.25,
) -> dict[str, object]:
    tokenized = [(_doc_id(doc), _tokenize(doc.get("text", ""))) for doc in docs]
    doc_count = len(tokenized)
    doc_len: dict[str, int] = {}
    df: dict[str, int] = {}
    postings: dict[str, list[tuple[str, int]]] = {}

    for doc_id, tokens in tokenized:
        doc_len[doc_id] = len(tokens)
        tf: dict[str, int] = {}
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
        for token, value in idf.copy().items():
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


def write_bm25_index(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def load_bm25_index(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}  # type: ignore[reportMissingTypeArgument]


def query_bm25_index(
    index: dict[str, object], question: str, top_k: int = 5
) -> list[tuple[str, float]]:
    tokens = _tokenize(question)
    if not tokens:
        return []

    idf = _as_float_dict(index.get("idf"))
    postings = _as_postings(index.get("postings"))
    doc_len = _as_float_dict(index.get("doc_len"))
    avgdl = _as_float(index.get("avgdl"))
    k1 = _as_float(index.get("k1"), default=1.2)
    b = _as_float(index.get("b"), default=0.75)
    if not postings or not doc_len or avgdl <= 0.0:
        return []

    scores: dict[str, float] = {}
    for token in set(tokens):
        token_idf = float(idf.get(token, 0.0))
        if token_idf <= 0.0:
            continue
        for doc_id, tf_i in postings.get(token, []):
            dl = float(doc_len.get(doc_id, 0.0))
            if dl <= 0.0:
                continue
            if tf_i <= 0.0:
                continue
            denom = tf_i + k1 * (1 - b + b * (dl / avgdl))
            if denom <= 0.0:
                continue
            inc = token_idf * (tf_i * (k1 + 1)) / denom
            scores[doc_id] = scores.get(doc_id, 0.0) + float(inc)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def _as_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_float_dict(raw: object) -> dict[str, float]:
    if not isinstance(raw, dict):  # type: ignore[reportMissingTypeArgument]
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        out[str(key)] = _as_float(value)
    return out


def _as_postings(raw: object) -> dict[str, list[tuple[str, float]]]:
    if not isinstance(raw, dict):  # type: ignore[reportMissingTypeArgument]
        return {}
    out: dict[str, list[tuple[str, float]]] = {}
    for key, value in raw.items():
        if not isinstance(value, list):  # type: ignore[reportMissingTypeArgument]
            continue
        cleaned: list[tuple[str, float]] = []
        for item in value:
            if not isinstance(item, list) or len(item) != 2:  # type: ignore[reportMissingTypeArgument]
                continue
            doc_id = str(item[0])
            tf_i = _as_float(item[1])
            if tf_i <= 0.0:
                continue
            cleaned.append((doc_id, tf_i))
        if cleaned:
            out[str(key)] = cleaned
    return out


def _doc_id(doc: dict[str, str]) -> str:
    return doc.get("doc_id", "")


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 3]
    # Add minimal CJK support: bigrams for Han runs.
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            tokens.append(run)
        else:
            for idx in range(len(run) - 1):
                tokens.append(run[idx : idx + 2])
    return tokens
