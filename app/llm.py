"""LLM через OpenAI (ChatGPT) Chat Completions или любой OpenAI-совместимый эндпоинт."""
from __future__ import annotations

from functools import lru_cache

from .config import settings
from .openai_rest import post


class OpenAILLM:
    def __init__(self) -> None:
        self._model_name = settings.openai_model

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        data = post(
            "/chat/completions",
            {
                "model": self._model_name,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=90,
        )
        return (data["choices"][0]["message"]["content"] or "").strip()


@lru_cache(maxsize=1)
def get_llm() -> OpenAILLM:
    return OpenAILLM()
