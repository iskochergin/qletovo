"""LLM-клиент. По умолчанию Yandex (yandexgpt-lite). Альтернатива — OpenAI-совместимый API."""
from __future__ import annotations

from functools import lru_cache

from .config import settings


class YandexLLM:
    def __init__(self) -> None:
        from yandex_cloud_ml_sdk import YCloudML

        if not settings.yandex_folder_id or not settings.yandex_api_key:
            raise RuntimeError("YANDEX_FOLDER_ID / YANDEX_API_KEY не заданы в .env")
        self._sdk = YCloudML(folder_id=settings.yandex_folder_id, auth=settings.yandex_api_key)
        self._model_name = settings.yandex_completion_model

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        model = self._sdk.models.completions(self._model_name).configure(temperature=temperature)
        out = model.run([{"role": "system", "text": system}, {"role": "user", "text": user}])
        return (out[0].text if out else "").strip()


class OpenAICompatLLM:
    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=settings.openai_base_url or None, api_key=settings.openai_api_key)
        self._model_name = settings.openai_model

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        resp = self._client.chat.completions.create(
            model=self._model_name,
            temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return (resp.choices[0].message.content or "").strip()


@lru_cache(maxsize=1)
def get_llm():
    if settings.llm_provider == "openai":
        return OpenAICompatLLM()
    return YandexLLM()
