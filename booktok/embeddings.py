from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import os
from typing import Iterable

from booktok.db import PROJECT_ROOT


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_CACHE = PROJECT_ROOT / ".model-cache" / "sentence-transformers"
VECTOR_SIZE = 384


class EmbeddingUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _load_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingUnavailable(
            "Install the local ML dependencies with setup.ps1 -WithML before using semantic search."
        ) from exc

    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    revision = os.environ.get("BOOKTOK_MODEL_REVISION") or None
    try:
        model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=str(MODEL_CACHE),
            device="cpu",
            revision=revision,
        )
    except Exception as exc:
        raise EmbeddingUnavailable(
            "The local sentence embedding model could not be loaded. Check the model cache and network connection."
        ) from exc

    config = getattr(getattr(model, "_first_module", lambda: None)(), "auto_model", None)
    config = getattr(config, "config", None)
    model_version = (
        getattr(config, "_commit_hash", None)
        or revision
        or "main"
    )
    return model, str(model_version)


def model_version() -> str:
    return _load_model()[1]


def _encode(texts: Iterable[str], query: bool = False) -> list[list[float]]:
    clean_texts = [str(text).strip() for text in texts]
    if not clean_texts:
        return []
    model, _ = _load_model()
    import numpy as np

    method = getattr(model, "encode_query" if query else "encode_document", None)
    if method is None:
        method = model.encode
    vectors = method(
        clean_texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
        batch_size=16,
    )
    return np.asarray(vectors, dtype=np.float32).tolist()


def encode_query(text: str) -> list[float]:
    return _encode([text], query=True)[0]


def encode_documents(texts: Iterable[str]) -> list[list[float]]:
    return _encode(texts)


def vector_literal(vector: Iterable[float]) -> str:
    values = [float(value) for value in vector]
    if len(values) != VECTOR_SIZE:
        raise ValueError(f"Expected a {VECTOR_SIZE}-dimension vector; got {len(values)}.")
    return "[" + ",".join(f"{value:.8g}" for value in values) + "]"


def text_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
