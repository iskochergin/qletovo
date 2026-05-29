"""RAG: retrieval -> контекст -> LLM -> ответ + детерминированные источники + отказы."""
from __future__ import annotations

import re
import unicodedata
import urllib.parse
from collections import defaultdict
from pathlib import Path

from .config import settings
from .llm import get_llm
from .prompts import JUNIOR_REDIRECT, NO_DATA, NO_DATA_USER, OFF_TOPIC, SYSTEM_PROMPT

# Вопрос явно про «Летово Джуниор» / начальную школу → перенаправляем на основную школу.
_JUNIOR_RE = re.compile(r"дж[ую]ниор|dzhunior|junior|начальн\w*\s+школ|младш\w*\s+школ|\bНОО\b|началк", re.I)
from .store import get_store


def _docs_map() -> dict[str, str]:
    """NFC-имя -> фактическое имя файла на диске (имена кириллические, сверка нормализованно)."""
    out: dict[str, str] = {}
    docs_dir = Path(settings.docs_dir)
    if docs_dir.exists():
        for p in docs_dir.iterdir():
            if p.is_file() and p.suffix.lower() == ".pdf":
                out[unicodedata.normalize("NFC", p.name)] = p.name
    return out


def resolve_local_filename(name: str | None) -> str | None:
    if not name:
        return None
    docs = _docs_map()
    norm = unicodedata.normalize("NFC", name)
    if norm in docs:
        return docs[norm]
    folded = norm.casefold()
    for key, value in docs.items():
        if key.casefold() == folded:
            return value
    return None


def pdf_page_url(local_name: str, page: int | None, base_url: str, title: str | None = None) -> str:
    """Ссылка на страницу-просмотрщик: {base}/viewer/<file>.pdf?page=N&title=...

    Просмотрщик (frontend/viewer.html) показывает PDF на нужной странице + топбар с кнопкой
    «назад в чат» и человекочитаемым названием документа.
    """
    actual = resolve_local_filename(local_name) or local_name
    base = (base_url or "").rstrip("/")
    quoted = urllib.parse.quote(actual)
    params = []
    if page:
        params.append(f"page={int(page)}")
    if title:
        params.append("title=" + urllib.parse.quote(title))
    query = ("?" + "&".join(params)) if params else ""
    return f"{base}/viewer/{quoted}{query}"


def _expand_by_pages(indices: list[int]) -> list[int]:
    """Лучшие чанки (ранжированные) + чанки соседних страниц (PAGE_WINDOW), с жёстким лимитом
    на общее число блоков (CONTEXT_MAX_BLOCKS), чтобы промпт не раздувался и ответ был быстрым."""
    store = get_store()
    chunks = store.chunks
    cap = max(settings.context_max_blocks, len(indices))
    selected = list(indices)  # ранжированные лучшие — в приоритете
    seen = set(indices)
    if settings.page_window >= 0:
        by_doc: dict[str, set[int]] = defaultdict(set)
        for i in indices:
            ch = chunks[i]
            if ch.get("page"):
                by_doc[ch.get("doc_id")].add(int(ch["page"]))
        wanted: dict[str, set[int]] = {}
        for doc_id, pages in by_doc.items():
            w: set[int] = set()
            for p in pages:
                for q in range(p - settings.page_window, p + settings.page_window + 1):
                    w.add(q)
            wanted[doc_id] = w
        for j, ch in enumerate(chunks):
            if len(selected) >= cap:
                break
            did = ch.get("doc_id")
            if j not in seen and did in wanted and int(ch.get("page") or 0) in wanted[did]:
                selected.append(j)
                seen.add(j)
    return selected[:cap]


def _build_context(indices: list[int]) -> str:
    store = get_store()
    blocks = []
    for n, i in enumerate(indices, 1):
        ch = store.chunks[i]
        title = ch.get("title") or "Документ"
        page = ch.get("page") or "—"
        text = ch["text"]
        if len(text) > settings.max_snippet:
            text = text[: settings.max_snippet] + "…"
        blocks.append(f"[Источник {n}] {title}, стр. {page}\n{text}")
    return "\n\n---\n\n".join(blocks)


def _build_sources(
    indices: list[int],
    base_url: str,
    sims: list[float] | None = None,
    limit: int = 3,
    margin: float = 0.07,
) -> list[dict]:
    store = get_store()
    # Отсекаем слабо релевантные источники: оставляем только близкие к лучшему по сходству.
    if sims:
        best = sims[0]
        indices = [i for i, s in zip(indices, sims) if s >= best - margin]
    out: list[dict] = []
    seen: set[tuple] = set()
    for i in indices:
        ch = store.chunks[i]
        local_name = resolve_local_filename(ch.get("local_name")) or ch.get("local_name") or "doc.pdf"
        try:
            page = int(ch.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        key = (ch.get("title"), page)
        if key in seen:
            continue
        seen.add(key)
        title = ch.get("title") or local_name
        out.append(
            {
                "title": title,
                "page": page,
                "url": pdf_page_url(local_name, page, base_url, title=title),
            }
        )
        if len(out) >= limit:
            break
    return out


_CITE_RE = re.compile(r"(?im)^[ \t>*\-]*источник[а-я]*\s*[:：]\s*([0-9 ,\.]+?)\s*$")


def _parse_cited(answer: str, context_idx: list[int]) -> tuple[list[int], str]:
    """Извлекает строку «ИСТОЧНИКИ: N, M» из ответа модели → индексы чанков + чистый текст.

    Номера — 1-based позиции блоков [Источник N] в порядке КОНТЕКСТА (context_idx).
    """
    matches = list(_CITE_RE.finditer(answer))
    if not matches:
        return [], answer
    m = matches[-1]
    nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
    cited = [context_idx[n - 1] for n in nums if 1 <= n <= len(context_idx)]
    clean = (answer[: m.start()] + answer[m.end():]).strip()
    return cited, clean


def _is_refusal(answer: str) -> bool:
    a = answer.strip().lower()
    return (
        "нет данных по этому вопросу" in a
        or "отвечаю только на вопросы" in a
        or a == NO_DATA.lower()
        or a == OFF_TOPIC.lower()
    )


def answer_question(question: str, base_url: str, temperature: float = 0.0, history: list[dict] | None = None) -> dict:
    question = (question or "").strip()
    if not question:
        return {"answer": OFF_TOPIC, "sources": [], "status": "off_topic"}

    # Вопросы про «Летово Джуниор»/начальную школу — отвечаем, что зона только основная школа.
    if _JUNIOR_RE.search(question):
        return {"answer": JUNIOR_REDIRECT, "sources": [], "status": "off_topic"}

    from .embeddings import get_embedder

    # Контекст диалога для поиска: к короткому уточнению («а разве не 8?») добавляем
    # предыдущий вопрос пользователя, иначе ретривал не найдёт нужные документы.
    prev_user = ""
    for turn in reversed(history or []):
        if turn.get("role") == "user" and (turn.get("content") or "").strip():
            prev_user = turn["content"].strip()[:300]
            break
    # Предыдущий вопрос добавляем к поиску ТОЛЬКО для коротких уточнений-фрагментов
    # («а разве не 8?»). Полноценный вопрос ищем как есть, чтобы прошлая тема его не «загрязняла».
    is_followup = len(question.split()) <= 4
    retrieval_text = f"{prev_user}\n{question}" if (prev_user and is_followup) else question

    store = get_store()
    qvec = get_embedder().embed_query(retrieval_text)
    top_idx, sims = store.search(qvec, settings.top_k)

    if not top_idx:
        return {"answer": NO_DATA_USER, "sources": [], "status": "not_found"}

    # Релевантностный гейт: явно нерелевантные вопросы (вне зоны школы) отсекаем до LLM.
    if sims and sims[0] < settings.offtopic_gate:
        return {"answer": OFF_TOPIC, "sources": [], "status": "off_topic"}

    best_idx = top_idx[: settings.best_k]
    best_sims = sims[: settings.best_k]
    context_idx = _expand_by_pages(best_idx)
    context = _build_context(context_idx)

    user_msg = f"КОНТЕКСТ:\n{context}\n\nВОПРОС: {question}"
    raw = get_llm().complete(SYSTEM_PROMPT, user_msg, temperature=temperature, history=history[-6:] if history else None)
    answer = (raw or "").strip()

    if not answer:
        return {"answer": NO_DATA_USER, "sources": [], "status": "not_found"}

    if _is_refusal(answer):
        if "отвечаю только на вопросы" in answer.lower():
            return {"answer": OFF_TOPIC, "sources": [], "status": "off_topic"}
        return {"answer": NO_DATA_USER, "sources": [], "status": "not_found"}

    # Источники — те блоки [Источник N], которые модель указала, что использовала.
    cited_idx, answer = _parse_cited(answer, context_idx)
    if not answer:  # на всякий случай: модель вернула только строку источников
        return {"answer": NO_DATA_USER, "sources": [], "status": "not_found"}
    if cited_idx:
        sources = _build_sources(cited_idx, base_url, limit=3)
    elif best_sims and best_sims[0] >= 0.35:
        # модель не указала источники, но ответ явно опирается на релевантные документы
        sources = _build_sources(best_idx, base_url, sims=best_sims, limit=3)
    else:
        # общий/разговорный ответ без опоры на конкретный документ — без источников
        sources = []
    return {"answer": answer, "sources": sources, "status": "answerable"}


def to_markdown(answer: str, sources: list[dict]) -> str:
    """Единый формат ответа с блоком «Источники» (используется ботом и как text в API)."""
    a = (answer or "").strip()
    if not sources:
        return a
    lines = ["", "Источники:"]
    for s in sources:
        title = s.get("title") or "Документ"
        page = s.get("page")
        url = s.get("url")
        suffix = f", стр. {page}" if page else ""
        if url:
            lines.append(f"• [{title}{suffix}]({url})")
        else:
            lines.append(f"• {title}{suffix}")
    return a + "\n" + "\n".join(lines)


def list_documents(base_url: str) -> list[dict]:
    store = get_store()
    out = []
    for m in store.manifest:
        local_name = resolve_local_filename(m.get("local_name")) or m.get("local_name")
        out.append(
            {
                "doc_id": m.get("doc_id"),
                "title": m.get("title"),
                "local_name": local_name,
                "page_count": m.get("page_count"),
                "n_chunks": m.get("n_chunks"),
                "url": pdf_page_url(local_name, 1, base_url, title=m.get("title")) if local_name else None,
            }
        )
    return out
