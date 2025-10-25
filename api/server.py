import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config import DOCS_DIR, CORS_ORIGINS
from rag_engine import llm_answer, to_telegram_md, list_manifest

class AskIn(BaseModel):
    question: str
    temperature: float | None = 0.0

class AskOut(BaseModel):
    text: str
    answer: str | list
    sources: list

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.mount("/files", StaticFiles(directory=DOCS_DIR), name="files")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/manifest")
def manifest(request: Request):
    base = str(request.base_url)
    return {"documents": list_manifest(base)}

@app.post("/ask", response_model=AskOut)
def ask(payload: AskIn, request: Request):
    base = str(request.base_url)
    data = llm_answer(payload.question.strip(), base, payload.temperature or 0.0)
    text = to_telegram_md(data.get("answer"), data.get("sources"))
    return AskOut(text=text, answer=data.get("answer"), sources=data.get("sources"))
