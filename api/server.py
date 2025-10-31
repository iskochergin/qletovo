from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from web.docs.site import iter_pdf_files, render_index_page, render_viewer_page

from .config import API_HOST, API_PORT, DOCS_DIR, CORS_ORIGINS, PUBLIC_BASE_URL
from .rag_engine import llm_answer, to_telegram_md, list_manifest, resolve_local_filename

class AskIn(BaseModel):
    question: str
    temperature: float | None = 0.0

class AskOut(BaseModel):
    text: str
    answer: str | list
    sources: list

DOCS_PATH = Path(DOCS_DIR)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.mount("/files", StaticFiles(directory=DOCS_DIR), name="files")
FAVICON_PATH = Path("media/qletovo-logo.ico")


@app.get("/", response_class=HTMLResponse)
def docs_index():
    files = iter_pdf_files(DOCS_DIR)
    items = [(file_path.name, f"/viewer/{quote(file_path.name)}") for file_path in files]
    return HTMLResponse(render_index_page(items))


def _resolve_public_base_url(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    return str(request.base_url).rstrip("/")


@app.get("/viewer/{local_name}", response_class=HTMLResponse)
def view_document(local_name: str, page: int = 1):
    safe_name = Path(local_name).name
    actual_name = resolve_local_filename(safe_name)
    if not actual_name:
        raise HTTPException(status_code=404, detail="Документ не найден.")
    target = DOCS_PATH / actual_name
    if not target.exists() or target.suffix.lower() != ".pdf":
        raise HTTPException(status_code=404, detail="Документ не найден.")
    display_name = target.name
    qname = quote(display_name)
    fragment = f"#page={page}" if page and page > 0 else ""
    pdf_url = f"/files/{qname}{fragment}"
    return HTMLResponse(render_viewer_page(display_name, pdf_url))

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/manifest")
def manifest(request: Request):
    base = _resolve_public_base_url(request)
    return list_manifest(base)

@app.post("/ask", response_model=AskOut)
def ask(payload: AskIn, request: Request):
    base = _resolve_public_base_url(request)
    data = llm_answer(payload.question.strip(), base, payload.temperature or 0.0)
    text = to_telegram_md(data.get("answer"), data.get("sources"))
    return AskOut(text=text, answer=data.get("answer"), sources=data.get("sources"))


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    if FAVICON_PATH.exists():
        from fastapi.responses import FileResponse

        return FileResponse(FAVICON_PATH, media_type="image/x-icon")

    return HTMLResponse(status_code=404, content="")


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=API_HOST, port=API_PORT)


if __name__ == "__main__":
    main()
