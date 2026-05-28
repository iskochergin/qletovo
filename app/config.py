"""Конфигурация загружается из .env (см. .env.example). Секреты в коде не хранятся.

LLM и эмбеддинги — через OpenAI (ChatGPT) API или любой OpenAI-совместимый эндпоинт.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # --- paths ---
    docs_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "docs")
    index_dir: Path = field(default_factory=lambda: BASE_DIR / "data" / "index")
    frontend_dir: Path = field(default_factory=lambda: BASE_DIR / "frontend")

    # --- OpenAI (ChatGPT) / OpenAI-совместимый эндпоинт ---
    openai_api_key: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    # Пусто => SDK использует https://api.openai.com/v1. Задайте для совместимого прокси.
    openai_base_url: str = field(default_factory=lambda: _get("OPENAI_BASE_URL"))
    openai_model: str = field(default_factory=lambda: _get("OPENAI_MODEL", "gpt-4o-mini"))
    openai_embed_model: str = field(
        default_factory=lambda: _get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    )

    # --- server ---
    api_host: str = field(default_factory=lambda: _get("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _get_int("API_PORT", 8765))
    public_base_url: str = field(default_factory=lambda: _get("PUBLIC_BASE_URL"))
    cors_origins: list[str] = field(default_factory=lambda: _get_list("CORS_ORIGINS", ["*"]))

    # --- admin ---
    admin_password: str = field(default_factory=lambda: _get("ADMIN_PASSWORD", "change-me"))

    # --- telegram ---
    telegram_token: str = field(default_factory=lambda: _get("TELEGRAM_TOKEN"))
    backend_url: str = field(default_factory=lambda: _get("BACKEND_URL", "http://127.0.0.1:8765"))

    # --- RAG params ---
    top_k: int = field(default_factory=lambda: _get_int("TOP_K", 10))
    best_k: int = field(default_factory=lambda: _get_int("BEST_K", 6))
    page_window: int = field(default_factory=lambda: _get_int("PAGE_WINDOW", 1))
    max_snippet: int = field(default_factory=lambda: _get_int("MAX_SNIPPET", 1200))
    chunk_chars: int = field(default_factory=lambda: _get_int("CHUNK_CHARS", 900))
    chunk_overlap: int = field(default_factory=lambda: _get_int("CHUNK_OVERLAP", 200))
    # Какие документы НЕ индексировать (regex по имени файла). По умолчанию исключаем
    # учебные программы/ООП/рабочие программы — это объёмные педагогические документы,
    # которые засоряют поиск по нормативным вопросам (приём, правила, оценивание, политики).
    index_exclude: str = field(
        default_factory=lambda: _get("INDEX_EXCLUDE", r"(?i)(?:^(?:OOP|RP|DOOP)|рабоч|programm|annotac|uchebny)")
    )
    # Порог релевантности: если лучшее сходство ниже — вопрос считается вне зоны школы.
    # Калибруется под модель эмбеддингов (для text-embedding-3-small см. README).
    offtopic_gate: float = field(default_factory=lambda: float(_get("OFFTOPIC_GATE", "0.30") or "0.30"))

    # --- crawler ---
    crawl_seeds: list[str] = field(
        default_factory=lambda: _get_list("CRAWL_SEEDS", ["https://letovo.ru", "https://qletovo.ru"])
    )
    crawl_delay: float = field(default_factory=lambda: float(_get("CRAWL_DELAY", "1.0") or "1.0"))
    crawl_max_pages: int = field(default_factory=lambda: _get_int("CRAWL_MAX_PAGES", 400))


settings = Settings()
