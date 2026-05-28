"""Тонкий клиент OpenAI REST на requests.

Почему не официальный SDK: связка openai-SDK + httpx ломает построение URL на Python 3.14
(UnsupportedProtocol при склейке base_url с относительным путём). requests с абсолютными URL
работает везде (и на 3.14 dev, и на 3.12 в Docker). API простой — обёртка минимальна.
"""
from __future__ import annotations

import time

import requests

from .config import settings


def base_url() -> str:
    return (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")


def _headers() -> dict[str, str]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY не задан в .env")
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def post(path: str, payload: dict, *, timeout: int = 60, retries: int = 4) -> dict:
    url = f"{base_url()}{path}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=_headers(), json=payload, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RuntimeError(f"OpenAI {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 — сетевые сбои / rate limit → retry
            last = exc
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"OpenAI request failed ({path}): {last!r}")
