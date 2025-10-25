from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from web.docs.site import iter_pdf_files, render_index_page, render_viewer_page

from .config import API_HOST, API_PORT, DOCS_DIR, CORS_ORIGINS
from .rag_engine import llm_answer, to_telegram_md, list_manifest

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


@app.get("/", response_class=HTMLResponse)
def docs_index():
    files = iter_pdf_files(DOCS_DIR)
    items = [(file_path.name, f"/viewer/{quote(file_path.name)}") for file_path in files]
    return HTMLResponse(render_index_page(items))


@app.get("/viewer/{local_name}", response_class=HTMLResponse)
def view_document(local_name: str, page: int = 1):
    safe_name = Path(local_name).name
    target = DOCS_PATH / safe_name
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
    base = str(request.base_url)
    return list_manifest(base)

@app.post("/ask", response_model=AskOut)
def ask(payload: AskIn, request: Request):
    base = str(request.base_url)
    data = llm_answer(payload.question.strip(), base, payload.temperature or 0.0)
    text = to_telegram_md(data.get("answer"), data.get("sources"))
    return AskOut(text=text, answer=data.get("answer"), sources=data.get("sources"))


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=API_HOST, port=API_PORT)


if __name__ == "__main__":
    main()
