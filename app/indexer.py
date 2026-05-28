"""Индексация: эмбеддинг чанков и запись в хранилище (инкрементально и полностью)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import settings
from .embeddings import get_embedder
from .ingest import build_chunks_for_pdf
from .store import get_store


def _load_source_urls(docs_dir: Path) -> dict[str, str]:
    """Карта local_name -> source_url из _sources.json (заполняется краулером)."""
    fp = docs_dir / "_sources.json"
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {name: (meta or {}).get("source_url") for name, meta in data.items() if (meta or {}).get("source_url")}


def _embed_for_index(chunk_dicts: list[dict]) -> np.ndarray:
    embedder = get_embedder()
    # Префикс задачи помогает мультиязычным моделям; для Yandex 'doc' это no-op по смыслу.
    texts = [c["text"] for c in chunk_dicts]
    return embedder.embed_docs(texts)


def index_pdf(path: Path, source_url: str | None = None) -> dict:
    """Инкрементально добавить/обновить один PDF в индексе. Возвращает manifest_entry."""
    path = Path(path)
    chunk_dicts, manifest_entry = build_chunks_for_pdf(path, source_url=source_url)
    vectors = _embed_for_index(chunk_dicts)
    get_store().add_document(manifest_entry, chunk_dicts, vectors)
    return manifest_entry


def reindex_all(docs_dir: Path | None = None) -> dict:
    """Полная пересборка индекса из всех PDF в docs_dir."""
    docs_dir = Path(docs_dir or settings.docs_dir)
    source_urls = _load_source_urls(docs_dir)
    pdfs = sorted(p for p in docs_dir.glob("*.pdf") if p.is_file())
    all_chunks: list[dict] = []
    all_manifest: list[dict] = []
    all_vectors: list[np.ndarray] = []
    for pdf in pdfs:
        chunk_dicts, manifest_entry = build_chunks_for_pdf(pdf, source_url=source_urls.get(pdf.name))
        if not chunk_dicts:
            continue
        vectors = _embed_for_index(chunk_dicts)
        all_chunks.extend(chunk_dicts)
        all_manifest.append(manifest_entry)
        all_vectors.append(vectors)
    if all_vectors:
        matrix = np.vstack(all_vectors)
    else:
        matrix = np.zeros((0, 0), dtype="float32")
    get_store().replace_all(all_chunks, matrix, all_manifest)
    return {
        "documents": len(all_manifest),
        "chunks": len(all_chunks),
        "dim": int(matrix.shape[1]) if matrix.size else 0,
    }
