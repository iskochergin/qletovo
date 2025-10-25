from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Iterable, List, Tuple

PACKAGE_DIR = Path(__file__).resolve().parent


def _load_asset(name: str) -> str:
    path = PACKAGE_DIR / name
    return path.read_text(encoding="utf-8")


STYLE = _load_asset("style.css")
BASE_TEMPLATE = _load_asset("base.html")
INDEX_TEMPLATE = _load_asset("index.html")
VIEWER_TEMPLATE = _load_asset("viewer.html")


def _wrap_page(header_html: str, body_html: str, *, title: str) -> str:
    return (
        BASE_TEMPLATE
        .replace("{{TITLE}}", title)
        .replace("{{STYLE}}", STYLE)
        .replace("{{HEADER}}", header_html)
        .replace("{{BODY}}", body_html)
    )


def render_index_page(files: Iterable[Tuple[str, str]]) -> str:
    entries: List[str] = []
    for name, href in files:
        entries.append(f'<li><a href="{escape(href, quote=True)}">{escape(name)}</a></li>')

    if entries:
        list_html = "\n".join(entries)
        body = INDEX_TEMPLATE.replace("{{ITEMS}}", list_html)
    else:
        body = '<p class="empty-state">PDF-файлы не найдены.</p>'

    header = '<h1 class="header-title">Документы «Летово»</h1>'
    return _wrap_page(header, body, title="Документы «Летово»")


def render_viewer_page(document_title: str, pdf_url: str) -> str:
    header = '<a class="header-back" href="/">← Ко всем документам</a>'
    body = (
        VIEWER_TEMPLATE
        .replace("{{PDF_URL}}", escape(pdf_url, quote=True))
        .replace("{{PDF_TITLE}}", escape(document_title))
    )
    return _wrap_page(header, body, title=document_title or "Документы «Летово»")


def iter_pdf_files(directory: str) -> List[Path]:
    base_path = Path(directory)
    if not base_path.exists():
        return []
    return sorted(
        [p for p in base_path.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"],
        key=lambda p: p.name.lower(),
    )
