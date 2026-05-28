"""Эмбеддинги. По умолчанию Yandex Cloud (256-dim, RU). Опционально OpenAI-совместимый."""
from __future__ import annotations

import time
from functools import lru_cache

import numpy as np

from .config import settings


class YandexEmbedder:
    """Yandex text_embeddings: модель 'doc' для индексации, 'query' для поиска."""

    def __init__(self) -> None:
        from yandex_cloud_ml_sdk import YCloudML

        if not settings.yandex_folder_id or not settings.yandex_api_key:
            raise RuntimeError("YANDEX_FOLDER_ID / YANDEX_API_KEY не заданы в .env")
        sdk = YCloudML(folder_id=settings.yandex_folder_id, auth=settings.yandex_api_key)
        self._doc = sdk.models.text_embeddings("doc")
        self._query = sdk.models.text_embeddings("query")

    def _run(self, model, text: str, retries: int = 3) -> np.ndarray:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                return np.asarray(model.run(text), dtype="float32")
            except Exception as exc:  # noqa: BLE001 — сетевые сбои Yandex
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Yandex embeddings failed: {last!r}")

    def embed_query(self, text: str) -> np.ndarray:
        return self._run(self._query, text)

    def embed_docs(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self._run(self._doc, t) for t in texts]) if texts else np.zeros((0, 256), "float32")


class OpenAIEmbedder:
    """Эмбеддинги через OpenAI-совместимый эндпоинт (одна модель для doc и query)."""

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=settings.openai_base_url or None, api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def embed_query(self, text: str) -> np.ndarray:
        resp = self._client.embeddings.create(model=self._model, input=text)
        return np.asarray(resp.data[0].embedding, dtype="float32")

    def embed_docs(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 1), "float32")
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return np.vstack([np.asarray(d.embedding, dtype="float32") for d in resp.data])


@lru_cache(maxsize=1)
def get_embedder():
    if settings.embeddings_provider == "openai":
        return OpenAIEmbedder()
    return YandexEmbedder()
