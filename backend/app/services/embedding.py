from __future__ import annotations

import logging
import math
import threading
from functools import lru_cache

from app.core.config import get_settings
from app.models.knowledge import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)
_model_lock = threading.Lock()


class EmbeddingServiceError(RuntimeError):
    pass


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, device="cpu")
    except Exception as error:
        logger.exception("Could not load sentence embedding model")
        raise EmbeddingServiceError("Embedding model could not be loaded") from error


def _model(model_name: str):
    with _model_lock:
        return _load_model(model_name)


def embed_texts(
    texts: list[str] | tuple[str, ...],
    *,
    model_name: str | None = None,
    batch_size: int | None = None,
) -> list[list[float]]:
    if not texts:
        raise ValueError("At least one text input is required")
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Text inputs must be non-empty strings")

    settings = get_settings()
    selected_model = model_name or settings.KNOWLEDGE_EMBEDDING_MODEL
    selected_batch_size = batch_size or settings.KNOWLEDGE_EMBEDDING_BATCH_SIZE
    if selected_batch_size < 1:
        raise ValueError("Embedding batch size must be at least one")

    try:
        with _model_lock:
            model = _load_model(selected_model)
            vectors = model.encode(
                list(texts),
                batch_size=selected_batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
    except EmbeddingServiceError:
        raise
    except Exception as error:
        logger.exception("Sentence embedding inference failed")
        raise EmbeddingServiceError("Embedding generation failed") from error

    if len(vectors) != len(texts):
        raise EmbeddingServiceError("Embedding model returned an invalid batch")
    results: list[list[float]] = []
    for vector in vectors:
        values = [float(value) for value in vector]
        if len(values) != EMBEDDING_DIMENSIONS or not all(
            math.isfinite(value) for value in values
        ):
            raise EmbeddingServiceError("Embedding model returned an invalid vector")
        if not any(values):
            raise EmbeddingServiceError("Embedding model returned an empty vector")
        results.append(values)
    return results


def embed_text(
    text: str,
    *,
    model_name: str | None = None,
) -> list[float]:
    return embed_texts([text], model_name=model_name)[0]
