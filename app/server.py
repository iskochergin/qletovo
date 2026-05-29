"""FastAPI: бэкенд веб-чата по документам школы «Летово».

Эндпоинты:
  POST /query            — задать вопрос (основной)
  GET  /manifest         — список проиндексированных документов
  GET  /health
  GET  /                 — Ч/Б веб-чат
  GET  /admin            — админка (пароль вводится на странице)
  POST /admin/login      — проверка пароля
  POST /admin/upload     — загрузка PDF (+ авто-индексация)
  POST /admin/reindex    — полная переиндексация
  POST /admin/delete     — удалить документ из индекса
  GET  /admin/docs       — список документов (для админки)
  /files/*               — статические PDF (источник для #page=N)
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .rag import answer_question, list_documents, to_markdown
from .store import get_store

settings.docs_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Летово — ассистент по документам", docs_url="/api-docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/files", StaticFiles(directory=str(settings.docs_dir)), name="files")

FRONTEND = Path(settings.frontend_dir)
MEDIA = Path(__file__).resolve().parent.parent / "media"
if MEDIA.exists():
    app.mount("/media", StaticFiles(directory=str(MEDIA)), name="media")


class QueryIn(BaseModel):
    question: str
    temperature: float | None = 0.0
    history: list[dict] | None = None  # [{role:"user"|"assistant", content:str}, ...]


class QueryOut(BaseModel):
    answer: str
    sources: list
    status: str
    text: str  # ответ + блок «Источники» (markdown)


def _base_url(request: Request) -> str:
    """Базовый URL для ссылок на PDF.

    Без хардкода домена: по умолчанию берём домен из самого запроса (какой адрес открыли —
    такие и ссылки), учитывая заголовки reverse-proxy (X-Forwarded-Proto/Host) — за nginx это
    даст публичный https-домен. PUBLIC_BASE_URL в .env — необязательный явный override
    (если нужен фиксированный канонический домен).
    """
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    fwd_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if fwd_host:
        scheme = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
        host = fwd_host.split(",")[0].strip()
        return f"{scheme}://{host}"
    return str(request.base_url).rstrip("/")


def require_admin(request: Request) -> None:
    supplied = request.headers.get("x-admin-password") or ""
    if not supplied:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:]
    if supplied != settings.admin_password:
        raise HTTPException(status_code=401, detail="Неверный пароль.")


# --- public API --------------------------------------------------------
@app.post("/query", response_model=QueryOut)
def query(payload: QueryIn, request: Request):
    data = answer_question(payload.question, _base_url(request), payload.temperature or 0.0, history=payload.history)
    return QueryOut(
        answer=data["answer"],
        sources=data["sources"],
        status=data["status"],
        text=to_markdown(data["answer"], data["sources"]),
    )


@app.get("/manifest")
def manifest(request: Request):
    return list_documents(_base_url(request))


@app.get("/health")
def health():
    store = get_store()
    return {"ok": True, "documents": len(store.manifest), "chunks": len(store)}


# --- admin API ---------------------------------------------------------
class LoginIn(BaseModel):
    password: str


@app.post("/admin/login")
def admin_login(payload: LoginIn):
    if payload.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Неверный пароль.")
    return {"ok": True}


@app.get("/admin/docs")
def admin_docs(request: Request, _: None = Depends(require_admin)):
    return list_documents(_base_url(request))


@app.post("/admin/upload")
async def admin_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    titles: list[str] = Form(default=[]),  # параллельно files: ручное название для каждого файла
    _: None = Depends(require_admin),
):
    from .indexer import index_pdf

    results = []
    for i, up in enumerate(files):
        name = unicodedata.normalize("NFC", Path(up.filename or "").name)
        if not name.lower().endswith(".pdf"):
            results.append({"filename": up.filename, "ok": False, "error": "Только PDF."})
            continue
        title = (titles[i].strip() if i < len(titles) else "") or None
        target = settings.docs_dir / name
        content = await up.read()
        target.write_bytes(content)
        try:
            entry = index_pdf(target, title=title)
            results.append({"filename": name, "ok": True, "doc_id": entry["doc_id"], "chunks": entry["n_chunks"]})
        except Exception as exc:  # noqa: BLE001
            results.append({"filename": name, "ok": False, "error": str(exc)[:300]})
    return {"results": results}


class RenameIn(BaseModel):
    doc_id: str
    title: str


@app.post("/admin/rename")
def admin_rename(payload: RenameIn, _: None = Depends(require_admin)):
    store = get_store()
    local_name = next((m.get("local_name") for m in store.manifest if m.get("doc_id") == payload.doc_id), None)
    ok = store.rename_document(payload.doc_id, payload.title)
    if ok and local_name:
        from .indexer import save_title_override

        save_title_override(local_name, payload.title)  # переживёт полную переиндексацию
    return {"ok": ok, "doc_id": payload.doc_id, "title": payload.title.strip()}


@app.post("/admin/reindex")
def admin_reindex(_: None = Depends(require_admin)):
    from .indexer import reindex_all

    return reindex_all()


class DeleteIn(BaseModel):
    doc_id: str
    delete_file: bool = True


@app.post("/admin/delete")
def admin_delete(payload: DeleteIn, _: None = Depends(require_admin)):
    store = get_store()
    local_name = None
    for m in store.manifest:
        if m.get("doc_id") == payload.doc_id:
            local_name = m.get("local_name")
            break
    removed = store.remove_document(payload.doc_id)
    if payload.delete_file and local_name:
        from .rag import resolve_local_filename

        actual = resolve_local_filename(local_name) or local_name
        fp = settings.docs_dir / actual
        if fp.exists():
            fp.unlink()
    return {"ok": removed, "doc_id": payload.doc_id}


# --- frontend ----------------------------------------------------------
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/", response_class=HTMLResponse)
def index():
    page = FRONTEND / "chat.html"
    if page.exists():
        return FileResponse(page, headers=_NO_CACHE)
    return HTMLResponse("<h1>Летово — ассистент</h1><p>frontend/chat.html не найден.</p>")


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    page = FRONTEND / "admin.html"
    if page.exists():
        return FileResponse(page, headers=_NO_CACHE)
    return HTMLResponse("<h1>Админка</h1><p>frontend/admin.html не найден.</p>")


@app.get("/viewer/{local_name:path}", response_class=HTMLResponse)
def viewer(local_name: str):
    # Просмотрщик PDF с топбаром (назад в чат + название). Имя/страница/название читаются на фронте.
    page = FRONTEND / "viewer.html"
    if page.exists():
        return FileResponse(page, headers=_NO_CACHE)
    return HTMLResponse("<h1>Просмотр документа</h1><p>frontend/viewer.html не найден.</p>")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    ico = MEDIA / "qletovo-logo.ico"
    if ico.exists():
        return FileResponse(ico, media_type="image/x-icon")
    return JSONResponse(status_code=404, content={})


def main() -> None:
    import uvicorn

    # proxy_headers/forwarded_allow_ips — чтобы за reverse-proxy ссылки получали публичный домен.
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
