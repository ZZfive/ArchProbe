import json
import importlib
import math
import os
import re
from pathlib import Path
from typing import Any, cast

DEFAULT_EMBED_MODEL = os.environ.get(
    "EMBED_MODEL_NAME", "jinaai/jina-embeddings-v2-base-code"
)


def _faiss_use_gpu_mode() -> str:
    value = os.environ.get("FAISS_USE_GPU", "auto").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return "1"
    if value in {"0", "false", "no", "off"}:
        return "0"
    return "auto"


def build_vector_index(
    docs: list[dict[str, str]], max_terms: int = 200
) -> dict[str, object]:
    del max_terms
    doc_ids = [str(doc.get("doc_id", "")) for doc in docs if str(doc.get("doc_id", ""))]
    texts = [str(doc.get("text", "")) for doc in docs if str(doc.get("doc_id", ""))]
    if not doc_ids:
        return {
            "backend": "empty",
            "doc_ids": [],
            "dim": 0,
            "model": DEFAULT_EMBED_MODEL,
        }

    embedder = _get_embedder()
    vectors = _embed_texts(embedder, texts)
    if vectors.size == 0:
        return {
            "backend": "empty",
            "doc_ids": [],
            "dim": 0,
            "model": DEFAULT_EMBED_MODEL,
        }

    dim = int(vectors.shape[1])
    index = _build_faiss_index(vectors, dim)
    return {
        "backend": "faiss",
        "doc_ids": doc_ids,
        "dim": dim,
        "model": DEFAULT_EMBED_MODEL,
        "_faiss_index": index,
    }


def write_vector_index(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backend = str(data.get("backend", ""))
    if backend == "faiss":
        faiss = _load_faiss()
        index = data.get("_faiss_index")
        if index is None:
            raise RuntimeError("missing FAISS index in build result")
        faiss_path = path.with_suffix(".faiss")
        faiss.write_index(index, str(faiss_path))
        manifest = {
            "backend": "faiss",
            "faiss_path": str(faiss_path),
            "doc_ids": data.get("doc_ids", []),
            "dim": _as_int(data.get("dim", 0)),
            "model": str(data.get("model", DEFAULT_EMBED_MODEL)),
        }
        path.write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
        )
        return

    path.write_text(
        json.dumps(
            {
                "backend": "empty",
                "doc_ids": [],
                "dim": 0,
                "model": DEFAULT_EMBED_MODEL,
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )


def load_vector_index(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    backend = str(raw.get("backend", ""))
    if backend != "faiss":
        return raw

    faiss = _load_faiss()
    faiss_path_raw = raw.get("faiss_path")
    if not isinstance(faiss_path_raw, str) or not faiss_path_raw:
        raise RuntimeError("invalid dense index manifest: missing faiss_path")
    faiss_path = Path(faiss_path_raw)
    if not faiss_path.exists():
        raise RuntimeError(f"dense index file not found: {faiss_path}")
    index = faiss.read_index(str(faiss_path))
    raw["_faiss_index"] = index
    return raw


def query_vector_index(
    index: dict[str, object], question: str, top_k: int = 5
) -> list[tuple[str, float]]:
    if not question.strip():
        return []
    backend = str(index.get("backend", ""))
    if backend != "faiss":
        return []

    faiss = _load_faiss()

    faiss_index = index.get("_faiss_index")
    doc_ids_raw = index.get("doc_ids")
    if faiss_index is None or not isinstance(doc_ids_raw, list) or not doc_ids_raw:
        return []
    doc_ids = [str(item) for item in doc_ids_raw]

    embedder = _get_embedder()
    query_vecs = _embed_texts(embedder, [question])
    if query_vecs.size == 0:
        return []

    k = max(1, min(top_k, len(doc_ids)))

    use_gpu = False
    gpu_mode = _faiss_use_gpu_mode()
    if gpu_mode != "0":
        get_num_gpus = getattr(faiss, "get_num_gpus", None)
        if callable(get_num_gpus):
            try:
                use_gpu = _as_int(get_num_gpus()) > 0
            except Exception:
                use_gpu = False
        if gpu_mode == "1" and not use_gpu:
            raise RuntimeError("FAISS_USE_GPU=1 but no FAISS GPU is available")

    search_index = faiss_index
    if use_gpu:
        cached_gpu = index.get("_faiss_index_gpu")
        if cached_gpu is None:
            cpu_to_gpu = getattr(faiss, "index_cpu_to_gpu", None)
            resources_cls = getattr(faiss, "StandardGpuResources", None)
            if not callable(cpu_to_gpu) or resources_cls is None:
                if gpu_mode == "1":
                    raise RuntimeError("FAISS GPU APIs not available in this build")
            else:
                try:
                    res = resources_cls()
                    gpu_index = cpu_to_gpu(res, 0, faiss_index)
                    index["_faiss_gpu_res"] = res
                    index["_faiss_index_gpu"] = gpu_index
                    cached_gpu = gpu_index
                except Exception:
                    if gpu_mode == "1":
                        raise
                    cached_gpu = None
        if cached_gpu is not None:
            search_index = cached_gpu

    search_fn = getattr(search_index, "search", None)
    if not callable(search_fn):
        raise RuntimeError("invalid FAISS index object")
    raw_result = search_fn(query_vecs, k)
    if not isinstance(raw_result, tuple) or len(raw_result) != 2:
        raise RuntimeError("invalid FAISS search result")
    distances = raw_result[0]
    indices = raw_result[1]
    if indices.size == 0:
        return []

    out: list[tuple[str, float]] = []
    for rank in range(k):
        idx = int(indices[0][rank])
        if idx < 0 or idx >= len(doc_ids):
            continue
        score = float(distances[0][rank])
        out.append((doc_ids[idx], score))
    return out


def _build_faiss_index(vectors, dim: int):
    faiss = _load_faiss()
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    return index


def _get_embedder():
    TextEmbedding = _load_fastembed_text_embedding()

    cache_dir = (
        os.environ.get("FASTEMBED_CACHE_DIR", "").strip()
        or os.environ.get("FASTEMBED_CACHE_PATH", "").strip()
    )
    if not cache_dir:
        raise RuntimeError(
            "FASTEMBED_CACHE_DIR (or FASTEMBED_CACHE_PATH) is required for offline embedding mode"
        )
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        raise RuntimeError(f"FASTEMBED_CACHE_DIR does not exist: {cache_path}")

    if (
        os.environ.get("HF_HUB_OFFLINE") != "1"
        or os.environ.get("TRANSFORMERS_OFFLINE") != "1"
    ):
        raise RuntimeError(
            "Offline mode required: set HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1"
        )

    device = os.environ.get("FASTEMBED_DEVICE", "auto").strip().lower() or "auto"
    if device not in {"auto", "cuda", "cpu"}:
        device = "auto"

    providers: list[object] | None = None
    want_cuda = device in {"auto", "cuda"}
    if want_cuda:
        try:
            ort = importlib.import_module("onnxruntime")
            get_providers = getattr(ort, "get_available_providers", None)
            if callable(get_providers):
                raw_available = get_providers()
                if isinstance(raw_available, list):
                    available = [str(p) for p in raw_available]
                else:
                    available = []
                if "CUDAExecutionProvider" in available:
                    providers = ["CUDAExecutionProvider"]
                elif device == "cuda":
                    raise RuntimeError(
                        "onnxruntime CUDAExecutionProvider not available"
                    )
        except Exception:
            if device == "cuda":
                raise
            providers = None

    try:
        if providers:
            return TextEmbedding(
                model_name=DEFAULT_EMBED_MODEL,
                cache_dir=cache_dir,
                providers=providers,
            )
        return TextEmbedding(model_name=DEFAULT_EMBED_MODEL, cache_dir=cache_dir)
    except TypeError:
        # Older fastembed versions may not accept providers/cuda args.
        if device == "cuda":
            raise
        return TextEmbedding(model_name=DEFAULT_EMBED_MODEL, cache_dir=cache_dir)


def _embed_texts(embedder, texts: list[str]):
    np = _load_numpy()
    vectors = list(embedder.embed(texts))
    if not vectors:
        return np.empty((0, 0), dtype="float32")
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim != 2:
        raise RuntimeError("embedding model returned invalid vector shape")
    return arr


def _load_numpy():
    try:
        return importlib.import_module("numpy")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("numpy is not installed (required for dense index)") from exc


def _load_faiss():
    try:
        return importlib.import_module("faiss")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("faiss is not installed (required for dense index)") from exc


def _load_fastembed_text_embedding():
    try:
        module = importlib.import_module("fastembed")
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "fastembed is not installed (required for local embeddings)"
        ) from exc
    TextEmbedding = getattr(module, "TextEmbedding", None)
    if TextEmbedding is None:
        raise RuntimeError("fastembed.TextEmbedding not available")
    return TextEmbedding


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _tokenize(text: str) -> list[str]:
    # Retained for compatibility with older sparse-index callers; no longer used.
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]+", text)
    tokens = [token.lower() for token in raw if len(token) >= 3]
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) == 1:
            tokens.append(run)
        else:
            for idx in range(len(run) - 1):
                tokens.append(run[idx : idx + 2])
    return tokens


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
