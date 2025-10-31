import os, re, json, urllib.parse, unicodedata, numpy as np
from collections import defaultdict
from pathlib import Path
from yandex_cloud_ml_sdk import YCloudML
from scipy.spatial.distance import cdist
from .config import INDEX_DIR, DOCS_DIR, FOLDER_ID, API_KEY, TOP_K, BEST_K, PAGE_WINDOW, MAX_SNIPPET, SYSTEM_JSON

chunks = json.load(open(os.path.join(INDEX_DIR, "chunks.json"), "r", encoding="utf-8"))
doc_vectors = np.load(os.path.join(INDEX_DIR, "vectors.npy"))
manifest_path = os.path.join(INDEX_DIR, "manifest.json")
manifest = json.load(open(manifest_path, "r", encoding="utf-8")) if os.path.exists(manifest_path) else []

sdk = YCloudML(folder_id=FOLDER_ID, auth=API_KEY)
emb_query = sdk.models.text_embeddings("query")

DOCS_PATH = Path(DOCS_DIR)
_AVAILABLE_DOCS = {}
if DOCS_PATH.exists():
    for file_path in DOCS_PATH.iterdir():
        if file_path.is_file():
            norm_name = unicodedata.normalize("NFC", file_path.name)
            _AVAILABLE_DOCS[norm_name] = file_path.name

def resolve_local_filename(name: str | None) -> str | None:
    if not name:
        return None
    norm = unicodedata.normalize("NFC", name)
    match = _AVAILABLE_DOCS.get(norm)
    if match:
        return match
    folded = norm.casefold()
    for key, value in _AVAILABLE_DOCS.items():
        if key.casefold() == folded:
            return value
    return None

def retrieve_local(question, k=TOP_K):
    qv = np.array(emb_query.run(question), dtype="float32")[None, :]
    d = cdist(qv, doc_vectors, metric="cosine")[0]
    idx = np.argsort(d)[:k]
    sims = 1 - d[idx]
    return idx, sims

def _block_text(ch):
    t = ch["text"]
    return t if len(t) <= MAX_SNIPPET else (t[:MAX_SNIPPET] + "…")

def _expand_by_pages(idx):
    selected = set(idx)
    by_doc = defaultdict(list)
    for i in idx:
        ch = chunks[i]
        by_doc[ch.get("doc_id")].append(ch.get("page"))
    for doc_id, pages in by_doc.items():
        centers = sorted(set(int(p) for p in pages if p))
        wanted_pages = set()
        for c in centers:
            for p in range(c - PAGE_WINDOW, c + PAGE_WINDOW + 1):
                wanted_pages.add(p)
        for j, ch in enumerate(chunks):
            if ch.get("doc_id") == doc_id and int(ch.get("page") or 0) in wanted_pages:
                selected.add(j)
    return sorted(selected)

def viewer_url(local_name: str, base_url: str, page: int | None = None) -> str:
    actual_local = resolve_local_filename(local_name) or local_name
    base = base_url.rstrip("/")
    qname = urllib.parse.quote(actual_local)
    suffix = f"/viewer/{qname}"
    query = f"?page={int(page)}" if page else ""
    return f"{base}{suffix}{query}"


def link_for(local_name: str, page: int, base_url: str):
    try:
        page_int = int(page)
    except (TypeError, ValueError):
        page_int = None
    return viewer_url(local_name, base_url, page_int)

def build_context(idx, base_url: str):
    expanded = _expand_by_pages(idx[:BEST_K])
    blocks = []
    for i in expanded:
        ch = chunks[i]
        title = ch.get("title") or ch.get("local_name") or "Документ"
        page = ch.get("page") or "—"
        local_name = resolve_local_filename(ch.get("local_name")) or os.path.basename(ch.get("path","doc.pdf"))
        url = link_for(local_name, page, base_url)
        blocks.append(f"[{title}; стр. {page}; файл: {url}]\n{_block_text(ch)}")
    return "\n\n---\n\n".join(blocks), expanded

_BULLET_RE = re.compile(r"^\s*(\d+)[\).\s]\s+(.*)$", flags=re.M)
def harvest_items_from_chunks(idxs):
    items = []
    for i in idxs:
        t = chunks[i]["text"]
        for m in _BULLET_RE.finditer(t):
            num = m.group(1).strip()
            body = m.group(2).strip()
            body = re.sub(r"\s*\.\s*$", "", body)
            items.append((int(num), body))
        if t.startswith("[ТАБЛИЦА]"):
            for line in t.splitlines():
                line = line.strip()
                if not line or line.startswith("[ТАБЛИЦА]"):
                    continue
                m = re.match(r"^(\d+)\s+(.+)$", line)
                if m:
                    num = int(m.group(1))
                    body = m.group(2).strip()
                    items.append((num, body))
    if not items:
        return []
    seen = set(); ordered = []
    for num, text in sorted(items, key=lambda x: (x[0], len(x[1]))):
        if num in seen:
            continue
        seen.add(num)
        ordered.append(f"{num}. {text}")
    return ordered

_ABCD_PATTERNS = [
    (r"[AaАа]\s*[:=\-–—]?\s*(\d+)", "A"),
    (r"[BbВв]\s*[:=\-–—]?\s*(\d+)", "B"),
    (r"[CcСс]\s*[:=\-–—]?\s*(\d+)", "C"),
    (r"[DdДд]\s*[:=\-–—]?\s*(\d+)", "D"),
]
def extract_abcd_scores(q: str):
    text = q.replace(",", " ").replace(";", " ")
    found = {}
    for pat, key in _ABCD_PATTERNS:
        m = re.search(pat, text)
        if m:
            try:
                found[key] = int(m.group(1))
            except Exception:
                pass
    if not all(k in found for k in ("A","B","C")):
        m = re.search(r"[AaАа]\s*,?\s*[BbВв]\s*,?\s*[CcСс]\s*[-–—=:]\s*(\d+)", text)
        if m:
            try:
                val = int(m.group(1))
                for k in ("A","B","C"):
                    found.setdefault(k, val)
            except Exception:
                pass
    hint = ""
    if found:
        total = sum(found.values())
        parts = [f"{k}={v}" for k, v in sorted(found.items())]
        hint = f"Подсказка: извлечено из вопроса → " + ", ".join(parts) + f"; сумма={total}."
    return found, hint

def _fix_json_common_issues(s: str) -> str:
    s = s.strip().strip('`').strip('*')
    m = re.search(r"<json>([\s\S]*?)</json>", s, flags=re.I)
    if m:
        s = m.group(1).strip()
    else:
        i, j = s.find("{"), s.rfind("}")
        if i != -1 and j != -1 and j > i:
            s = s[i:j+1]
    s = s.replace("“","\"").replace("”","\"").replace("„","\"").replace("‟","\"").replace("’","'").replace("‘","'")
    if re.search(r"(^|[{\[,]\s*)'(.*?)'\s*:", s) or re.search(r":\s*'(.*?)'(\s*[}\],])", s):
        s = re.sub(r"(?<!\\)'", '"', s)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s

def _safe_json_loads(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        fixed = _fix_json_common_issues(raw)
        try:
            return json.loads(fixed)
        except Exception:
            return {"status":"error","answer": fixed[:800], "sources":[]}

def _coerce_answer_text(ans):
    if isinstance(ans, (list, tuple)):
        lines = []
        for i, item in enumerate(ans, 1):
            item = "; ".join(map(str, item)) if isinstance(item, (list, tuple)) else str(item)
            item = item.strip()
            if not re.match(r"^\d+\.\s", item):
                item = f"{i}. {item}"
            lines.append(item)
        return "\n".join(lines)
    return (str(ans) if ans is not None else "").strip()

def build_sources_from_idx(idx, base_url: str, limit=3):
    res = []
    seen = set()
    for i in idx:
        ch = chunks[i]
        key = (ch.get("title"), ch.get("page"))
        if key in seen:
            continue
        seen.add(key)
        local_name = resolve_local_filename(ch.get("local_name")) or os.path.basename(ch.get("path","doc.pdf"))
        try:
            page_num = int(ch.get("page") or 1)
        except (TypeError, ValueError):
            page_num = 1
        res.append({
            "title": ch.get("title") or local_name or "Документ",
            "page": page_num,
            "url": link_for(local_name, page_num, base_url)
        })
        if len(res) >= limit:
            break
    return res

def llm_answer(question: str, base_url: str, temperature: float = 0.0) -> dict:
    idx_all, _ = retrieve_local(question, TOP_K)
    idx = idx_all[:BEST_K]
    context, expanded = build_context(idx, base_url)
    need_full_list = any(w in question.lower() for w in ["перечисл", "этап", "пунк", "список", "таблиц"])
    hint_list = harvest_items_from_chunks(expanded) if need_full_list else []
    list_hint_block = ("\n\nПодсказка: найденные пункты (полный список, используй их как ответ):\n" + "\n".join(hint_list)) if hint_list else ""
    _, scores_hint = extract_abcd_scores(question)
    scores_hint_block = f"\n\n{scores_hint}" if scores_hint else ""
    msgs = [
        {"role":"system","text": SYSTEM_JSON},
        {"role":"user","text": f"Контекст:\n{context}\n\nВопрос: {question}{list_hint_block}{scores_hint_block}"}
    ]
    out = sdk.models.completions("yandexgpt-lite").configure(temperature=temperature).run(msgs)
    raw = out[0].text if out else ""
    data = _safe_json_loads(raw)
    answer_text = _coerce_answer_text(data.get("answer"))
    if answer_text == "Нет данных в предоставленном контексте.":
        data["sources"] = []
        data["status"] = "not_found"
    elif not data.get("sources"):
        data["sources"] = build_sources_from_idx(idx, base_url, limit=3)
    if "status" not in data:
        data["status"] = "answerable" if data.get("answer") else "not_found"
    return data

def to_telegram_md(answer: str | list, sources: list) -> str:
    a = _coerce_answer_text(answer)
    if a.strip() == "Нет данных в предоставленном контексте.":
        return "Нет данных в предоставленном контексте."
    links = []
    for s in sources or []:
        title = s.get("title") or "Документ"
        page = s.get("page")
        url = s.get("url")
        if url:
            links.append(f"• [{title}]({url})" + (f" — стр. {page}" if page else ""))
        else:
            links.append(f"• {title}" + (f" — стр. {page}" if page else ""))
    links_md = "\n".join(links) if links else "• —"
    return f"{a}\n\nДокументы:\n{links_md}"

def list_manifest(base_url: str):
    out = []
    for m in manifest:
        requested = m.get("local_name") or os.path.basename(m.get("path","doc.pdf"))
        local_name = resolve_local_filename(requested)
        if not local_name:
            continue
        out.append({
            "doc_id": m.get("doc_id"),
            "title": m.get("title"),
            "local_name": local_name,
            "url": viewer_url(local_name, base_url),
        })
    return out
