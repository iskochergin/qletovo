"""Эмбеддинги через OpenAI (text-embedding-3-*). Одна модель для документов и запросов."""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .config import settings
from .openai_rest import post

_BATCH = 256  # сколько чанков слать в один запрос embeddings (лимит OpenAI — до 2048)


class OpenAIEmbedder:
    def __init__(self) -> None:
        self._model = settings.openai_embed_model

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        data = post("/embeddings", {"model": self._model, "input": inputs}, timeout=60)
        # сортируем по index на случай, если порядок не гарантирован
        rows = sorted(data["data"], key=lambda d: d.get("index", 0))
        return [r["embedding"] for r in rows]

    def embed_query(self, text: str) -> np.ndarray:
        return np.asarray(self._embed([text])[0], dtype="float32")

    def embed_docs(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), "float32")
        vectors: list[list[float]] = []
        for i in range(0, len(texts), _BATCH):
            vectors.extend(self._embed(texts[i : i + _BATCH]))
        return np.asarray(vectors, dtype="float32")


@lru_cache(maxsize=1)
def get_embedder() -> OpenAIEmbedder:
    return OpenAIEmbedder()
