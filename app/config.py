"""Конфигурация загружается из .env (см. .env.example). Секреты в коде не хранятся."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Yandex SDK по умолчанию шумит на DEBUG (включая метаданные запросов) — приглушаем.
for _name in ("yandex_cloud_ml_sdk", "yandex_ai_studio_sdk", "grpc"):
    logging.getLogger(_name).setLevel(logging.WARNING)


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

    # --- LLM ---
    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "yandex"))
    # Yandex
    yandex_folder_id: str = field(default_factory=lambda: _get("YANDEX_FOLDER_ID"))
    yandex_api_key: str = field(default_factory=lambda: _get("YANDEX_API_KEY"))
    yandex_completion_model: str = field(
        default_factory=lambda: _get("YANDEX_COMPLETION_MODEL", "yandexgpt-lite")
    )
    # OpenAI-compatible (used when LLM_PROVIDER=openai)
    openai_base_url: str = field(default_factory=lambda: _get("OPENAI_BASE_URL"))
    openai_api_key: str = field(default_factory=lambda: _get("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: _get("OPENAI_MODEL", "gpt-4o-mini"))

    # --- embeddings (Yandex; разделяет folder/key с LLM) ---
    embeddings_provider: str = field(
        default_factory=lambda: _get("EMBEDDINGS_PROVIDER", "yandex")
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
    # Порог релевантности: если лучшее сходство ниже — вопрос считается вне зоны школы.
    offtopic_gate: float = field(default_factory=lambda: float(_get("OFFTOPIC_GATE", "0.30") or "0.30"))

    # --- crawler ---
    crawl_seeds: list[str] = field(
        default_factory=lambda: _get_list("CRAWL_SEEDS", ["https://letovo.ru", "https://qletovo.ru"])
    )
    crawl_delay: float = field(default_factory=lambda: float(_get("CRAWL_DELAY", "1.0") or "1.0"))
    crawl_max_pages: int = field(default_factory=lambda: _get_int("CRAWL_MAX_PAGES", 400))


settings = Settings()
