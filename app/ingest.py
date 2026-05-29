"""PDF -> постраничные чанки с перекрытием (PyMuPDF). Номер страницы сохраняется в метаданных."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

from .config import settings
from .schools import school_of

_WS = re.compile(r"[ \t ]+")
_NL = re.compile(r"\n{3,}")


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r", "\n")
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()


def humanize_title(path: Path, doc: "fitz.Document") -> str:
    meta_title = (doc.metadata or {}).get("title", "") if doc else ""
    meta_title = (meta_title or "").strip()
    if 5 <= len(meta_title) <= 120 and meta_title.lower() not in {"untitled", "untitled document"}:
        return meta_title
    stem = path.stem
    stem = stem.replace("_", " ")
    return stem.strip()


def doc_id_for(path: Path, sha1: str) -> str:
    return f"{path.stem}-{sha1[:10]}"


def split_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:  # попытаться разорвать по границе слова/абзаца
            window = text[start:end]
            brk = max(window.rfind("\n"), window.rfind(". "), window.rfind(" "))
            if brk > size // 2:
                end = start + brk + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def build_chunks_for_pdf(path: Path, source_url: str | None = None) -> tuple[list[dict], dict]:
    """Возвращает (chunk_dicts без векторов, manifest_entry без n_chunks)."""
    path = Path(path)
    sha1 = file_sha1(path)
    doc = fitz.open(path)
    try:
        title = humanize_title(path, doc)
        doc_id = doc_id_for(path, sha1)
        local_name = unicodedata.normalize("NFC", path.name)
        school = school_of(local_name, title)
        chunk_dicts: list[dict] = []
        for page_index in range(doc.page_count):
            page_text = clean_text(doc[page_index].get_text("text"))
            if not page_text:
                continue
            for piece in split_text(page_text, settings.chunk_chars, settings.chunk_overlap):
                chunk_dicts.append(
                    {
                        "doc_id": doc_id,
                        "title": title,
                        "local_name": local_name,
                        "source_url": source_url,
                        "school": school,
                        "page": page_index + 1,  # человекочитаемая нумерация = #page=N
                        "text": piece,
                    }
                )
        manifest_entry = {
            "doc_id": doc_id,
            "title": title,
            "local_name": local_name,
            "source_url": source_url,
            "school": school,
            "page_count": doc.page_count,
            "sha1": sha1,
            "n_chunks": len(chunk_dicts),
        }
        return chunk_dicts, manifest_entry
    finally:
        doc.close()
