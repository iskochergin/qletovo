"""LLM через OpenAI (ChatGPT) Chat Completions или любой OpenAI-совместимый эндпоинт."""
from __future__ import annotations

from functools import lru_cache

from .config import settings
from .openai_rest import post


class OpenAILLM:
    def __init__(self) -> None:
        self._model_name = settings.openai_model

    def complete(self, system: str, user: str, temperature: float = 0.0, history: list[dict] | None = None) -> str:
        messages = [{"role": "system", "content": system}]
        for turn in history or []:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user})
        data = post(
            "/chat/completions",
            {"model": self._model_name, "temperature": temperature, "messages": messages},
            timeout=90,
        )
        return (data["choices"][0]["message"]["content"] or "").strip()


@lru_cache(maxsize=1)
def get_llm() -> OpenAILLM:
    return OpenAILLM()
