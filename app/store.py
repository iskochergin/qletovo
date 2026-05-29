"""Векторное хранилище: numpy flat-cosine + JSON-метаданные.

Простое и без внешней инфраструктуры (приоритет — простота хостинга). Поддерживает
инкрементальное добавление/удаление документа без полного пересчёта эмбеддингов.

Файлы в data/index/:
  - chunks.json   список чанков с метаданными
  - vectors.npy   матрица эмбеддингов (N x D), порядок строк = порядок chunks
  - manifest.json список документов
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import numpy as np

from .config import settings


def _atomic_write_bytes(path: Path, write_fn) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        write_fn(fh)
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class VectorStore:
    def __init__(self, index_dir: Path | None = None) -> None:
        self.index_dir = Path(index_dir or settings.index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.chunks: list[dict] = []
        self.manifest: list[dict] = []
        self.vectors = np.zeros((0, 0), dtype="float32")
        self._normed = np.zeros((0, 0), dtype="float32")
        self.load()

    # --- persistence ---------------------------------------------------
    @property
    def _chunks_path(self) -> Path:
        return self.index_dir / "chunks.json"

    @property
    def _vectors_path(self) -> Path:
        return self.index_dir / "vectors.npy"

    @property
    def _manifest_path(self) -> Path:
        return self.index_dir / "manifest.json"

    def load(self) -> None:
        with self._lock:
            if self._chunks_path.exists():
                self.chunks = json.loads(self._chunks_path.read_text(encoding="utf-8"))
            else:
                self.chunks = []
            if self._manifest_path.exists():
                self.manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            else:
                self.manifest = []
            if self._vectors_path.exists():
                self.vectors = np.load(self._vectors_path).astype("float32")
            else:
                self.vectors = np.zeros((0, 0), dtype="float32")
            self._recompute_norm()

    def save(self) -> None:
        with self._lock:
            _atomic_write_json(self._chunks_path, self.chunks)
            _atomic_write_json(self._manifest_path, self.manifest)
            _atomic_write_bytes(self._vectors_path, lambda fh: np.save(fh, self.vectors))

    def _recompute_norm(self) -> None:
        if self.vectors.size == 0:
            self._normed = self.vectors
            return
        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._normed = self.vectors / norms

    # --- read ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self.chunks)

    def has_doc(self, doc_id: str) -> bool:
        return any(m.get("doc_id") == doc_id for m in self.manifest)

    def has_sha1(self, sha1: str) -> bool:
        return any(m.get("sha1") == sha1 for m in self.manifest)

    def search(self, query_vec: np.ndarray, k: int) -> tuple[list[int], list[float]]:
        with self._lock:
            if self._normed.size == 0 or len(self.chunks) == 0:
                return [], []
            q = np.asarray(query_vec, dtype="float32").ravel()
            if q.shape[0] != self._normed.shape[1]:
                # Размерность запроса не совпадает с индексом (сменили модель эмбеддингов?).
                # Не падаем — индекс нужно пересобрать: python -m scripts.reindex
                return [], []
            qn = q / (np.linalg.norm(q) or 1.0)
            sims = self._normed @ qn
            k = min(k, sims.shape[0])
            idx = np.argpartition(-sims, k - 1)[:k]
            idx = idx[np.argsort(-sims[idx])]
            out_idx, out_sim = [], []
            for i in idx:
                s = float(sims[i])
                if s == float("-inf"):
                    continue
                out_idx.append(int(i))
                out_sim.append(s)
            return out_idx, out_sim

    # --- write (incremental) ------------------------------------------
    def add_document(self, manifest_entry: dict, chunk_dicts: list[dict], vectors: np.ndarray) -> None:
        """Добавляет один документ. Эмбеддинги считаются только для его чанков."""
        with self._lock:
            if not chunk_dicts:
                return
            vectors = np.asarray(vectors, dtype="float32")
            if vectors.shape[0] != len(chunk_dicts):
                raise ValueError("vectors/chunks length mismatch")
            self.remove_document(manifest_entry["doc_id"], save=False)  # idempotent replace
            self.chunks.extend(chunk_dicts)
            if self.vectors.size == 0:
                self.vectors = vectors.copy()
            else:
                if self.vectors.shape[1] != vectors.shape[1]:
                    raise ValueError("embedding dim mismatch with existing index")
                self.vectors = np.vstack([self.vectors, vectors])
            self.manifest.append(manifest_entry)
            self._recompute_norm()
            self.save()

    def remove_document(self, doc_id: str, *, save: bool = True) -> bool:
        with self._lock:
            keep_rows = [i for i, ch in enumerate(self.chunks) if ch.get("doc_id") != doc_id]
            removed = len(keep_rows) != len(self.chunks)
            if removed:
                self.chunks = [self.chunks[i] for i in keep_rows]
                if self.vectors.size:
                    self.vectors = self.vectors[keep_rows] if keep_rows else np.zeros((0, self.vectors.shape[1]), "float32")
                self.manifest = [m for m in self.manifest if m.get("doc_id") != doc_id]
                self._recompute_norm()
                if save:
                    self.save()
            return removed

    def replace_all(self, chunk_dicts: list[dict], vectors: np.ndarray, manifest: list[dict]) -> None:
        """Полная пересборка индекса (scripts/reindex.py)."""
        with self._lock:
            self.chunks = list(chunk_dicts)
            self.vectors = np.asarray(vectors, dtype="float32")
            self.manifest = list(manifest)
            self._recompute_norm()
            self.save()


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_store() -> VectorStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = VectorStore()
        return _store
