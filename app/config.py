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
    # reasoning_effort для gpt-5* (minimal|low|medium|high). low — баланс скорость/качество.
    reasoning_effort: str = field(default_factory=lambda: _get("REASONING_EFFORT", "low"))
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

    # --- RAG params ---
    top_k: int = field(default_factory=lambda: _get_int("TOP_K", 10))
    best_k: int = field(default_factory=lambda: _get_int("BEST_K", 6))
    page_window: int = field(default_factory=lambda: _get_int("PAGE_WINDOW", 1))
    max_snippet: int = field(default_factory=lambda: _get_int("MAX_SNIPPET", 1200))
    chunk_chars: int = field(default_factory=lambda: _get_int("CHUNK_CHARS", 900))
    chunk_overlap: int = field(default_factory=lambda: _get_int("CHUNK_OVERLAP", 200))
    # OCR для сканов: если на странице меньше ocr_min_page_chars текста — распознаём картинку.
    ocr_enabled: bool = field(default_factory=lambda: _get("OCR_ENABLED", "1") not in ("0", "false", "False", ""))
    ocr_min_page_chars: int = field(default_factory=lambda: _get_int("OCR_MIN_PAGE_CHARS", 80))
    ocr_lang: str = field(default_factory=lambda: _get("OCR_LANG", "rus+eng"))
    ocr_dpi: int = field(default_factory=lambda: _get_int("OCR_DPI", 200))
    # Жёсткий потолок на число блоков в контексте LLM — чтобы промпт не раздувался и ответ был быстрым.
    context_max_blocks: int = field(default_factory=lambda: _get_int("CONTEXT_MAX_BLOCKS", 12))
    # MMR-диверсификация выдачи: уменьшает дубли, в контекст попадают разные релевантные документы.
    mmr_enabled: bool = field(default_factory=lambda: _get("MMR_ENABLED", "1") not in ("0", "false", "False", ""))
    mmr_pool: int = field(default_factory=lambda: _get_int("MMR_POOL", 50))
    mmr_lambda: float = field(default_factory=lambda: float(_get("MMR_LAMBDA", "0.6") or "0.6"))
    # Query-expansion (RAG-fusion): LLM генерирует переформулировки, результаты сливаются по RRF.
    # Снижает чувствительность поиска к формулировке. Стоит +1 LLM-вызов на запрос.
    query_expansion: bool = field(default_factory=lambda: _get("QUERY_EXPANSION", "1") not in ("0", "false", "False", ""))
    query_expansion_n: int = field(default_factory=lambda: _get_int("QUERY_EXPANSION_N", 3))
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
