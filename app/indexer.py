"""Индексация: эмбеддинг чанков и запись в хранилище (инкрементально и полностью)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from .config import settings
from .embeddings import get_embedder
from .ingest import build_chunks_for_pdf
from .store import get_store


def is_excluded(local_name: str) -> bool:
    """Документы, исключённые из индекса по INDEX_EXCLUDE (учебные программы и т.п.)."""
    pat = settings.index_exclude
    return bool(pat) and re.search(pat, local_name or "") is not None


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


def _titles_path(docs_dir: Path) -> Path:
    return Path(docs_dir) / "_titles.json"


def load_title_overrides(docs_dir: Path | None = None) -> dict[str, str]:
    """Ручные названия документов (local_name -> title). Переживают полную переиндексацию."""
    fp = _titles_path(Path(docs_dir or settings.docs_dir))
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_title_override(local_name: str, title: str, docs_dir: Path | None = None) -> None:
    docs_dir = Path(docs_dir or settings.docs_dir)
    data = load_title_overrides(docs_dir)
    title = (title or "").strip()
    if title:
        data[local_name] = title
    else:
        data.pop(local_name, None)
    _titles_path(docs_dir).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _embed_for_index(chunk_dicts: list[dict]) -> np.ndarray:
    embedder = get_embedder()
    texts = [c["text"] for c in chunk_dicts]
    return embedder.embed_docs(texts)


def index_pdf(path: Path, source_url: str | None = None, title: str | None = None) -> dict:
    """Инкрементально добавить/обновить один PDF в индексе. Возвращает manifest_entry."""
    path = Path(path)
    if title:
        save_title_override(path.name, title)
    chunk_dicts, manifest_entry = build_chunks_for_pdf(path, source_url=source_url, title_override=title)
    vectors = _embed_for_index(chunk_dicts)
    get_store().add_document(manifest_entry, chunk_dicts, vectors)
    return manifest_entry


def reindex_all(docs_dir: Path | None = None) -> dict:
    """Полная пересборка индекса из всех PDF в docs_dir."""
    docs_dir = Path(docs_dir or settings.docs_dir)
    source_urls = _load_source_urls(docs_dir)
    title_overrides = load_title_overrides(docs_dir)
    pdfs = sorted(p for p in docs_dir.glob("*.pdf") if p.is_file())
    all_chunks: list[dict] = []
    all_manifest: list[dict] = []
    skipped: list[str] = []
    for pdf in pdfs:
        if is_excluded(pdf.name):
            skipped.append(f"{pdf.name}: исключён по INDEX_EXCLUDE")
            continue
        try:
            chunk_dicts, manifest_entry = build_chunks_for_pdf(
                pdf, source_url=source_urls.get(pdf.name), title_override=title_overrides.get(pdf.name)
            )
        except Exception as exc:  # noqa: BLE001 — битый/нечитаемый PDF не должен ронять реиндексацию
            skipped.append(f"{pdf.name}: {exc}")
            continue
        if not chunk_dicts:  # пустой текст (скан без OCR)
            skipped.append(f"{pdf.name}: нет извлекаемого текста")
            continue
        all_chunks.extend(chunk_dicts)
        all_manifest.append(manifest_entry)
    # Эмбеддим все чанки одним проходом (батчи внутри embed_docs) — минимум запросов к API.
    matrix = _embed_for_index(all_chunks) if all_chunks else np.zeros((0, 0), dtype="float32")
    get_store().replace_all(all_chunks, matrix, all_manifest)
    return {
        "documents": len(all_manifest),
        "chunks": len(all_chunks),
        "dim": int(matrix.shape[1]) if matrix.size else 0,
        "skipped": len(skipped),
        "skipped_detail": skipped[:20],
    }


def prune_index() -> dict:
    """Удаляет из УЖЕ собранного индекса документы, попадающие под INDEX_EXCLUDE,
    не пересчитывая эмбеддинги (векторы уже есть). Быстрый способ перечистить индекс."""
    store = get_store()
    keep = [i for i, ch in enumerate(store.chunks) if not is_excluded(ch.get("local_name", ""))]
    chunks = [store.chunks[i] for i in keep]
    vectors = store.vectors[keep] if store.vectors.size and keep else (
        store.vectors if keep else np.zeros((0, store.vectors.shape[1] if store.vectors.size else 0), "float32")
    )
    kept_docs = {ch["doc_id"] for ch in chunks}
    manifest = [m for m in store.manifest if m.get("doc_id") in kept_docs]
    removed = len(store.chunks) - len(chunks)
    store.replace_all(chunks, np.asarray(vectors, dtype="float32"), manifest)
    return {"kept_docs": len(manifest), "kept_chunks": len(chunks), "removed_chunks": removed}
