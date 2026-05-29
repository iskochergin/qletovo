"""LLM через OpenAI (ChatGPT) Chat Completions или любой OpenAI-совместимый эндпоинт."""
from __future__ import annotations

import re
from functools import lru_cache

from .config import settings
from .openai_rest import post

_EXPAND_SYS = (
    "Ты помогаешь искать в официальных документах школы «Летово». По вопросу пользователя дай "
    "несколько РАЗНЫХ по смыслу и ШИРОТЕ поисковых запросов, чтобы наверняка найти нужный фрагмент:\n"
    "- 1 переформулировка официальной лексикой документов;\n"
    "- 1 КОРОТКИЙ запрос из 2–3 ключевых слов — только главное понятие (термин), БЕЗ лишних "
    "уточнений из вопроса;\n"
    "- 1 запрос по более ШИРОКОЙ теме/смежному термину (например, вместо «стипендия на обучение» — "
    "«финансовая помощь», «Стипендиальный фонд», «льготы»).\n"
    "Не тащи во все запросы одни и те же уточняющие слова из вопроса. Только сами запросы, "
    "каждый с новой строки, без нумерации и пояснений."
)


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
        payload = {"model": self._model_name, "messages": messages}
        if self._model_name.lower().startswith("gpt-5"):
            # gpt-5*: temperature только дефолтная; reasoning_effort=low — быстрее в разы.
            payload["reasoning_effort"] = settings.reasoning_effort
        else:
            payload["temperature"] = temperature
        data = post("/chat/completions", payload, timeout=90)
        return (data["choices"][0]["message"]["content"] or "").strip()

    def expand_queries(self, question: str, n: int = 3) -> list[str]:
        """Сгенерировать n переформулировок вопроса для устойчивого поиска (RAG-fusion).
        При сбое возвращает пустой список — поиск тогда идёт только по исходному запросу."""
        try:
            payload = {
                "model": self._model_name,
                "messages": [
                    {"role": "system", "content": _EXPAND_SYS},
                    {"role": "user", "content": f"Вопрос: {question}\nДай {n} поисковых запроса."},
                ],
            }
            if self._model_name.lower().startswith("gpt-5"):
                payload["reasoning_effort"] = "minimal"  # переформулировки — простая задача, быстрее
            else:
                payload["temperature"] = 0.3
            data = post("/chat/completions", payload, timeout=30)
            text = data["choices"][0]["message"]["content"] or ""
        except Exception:
            return []
        out = []
        for line in text.splitlines():
            s = re.sub(r"^\s*[\d.\-–•)]+\s*", "", line).strip().strip('"«»')
            if s and s.lower() != question.lower():
                out.append(s)
        return out[:n]


@lru_cache(maxsize=1)
def get_llm() -> OpenAILLM:
    return OpenAILLM()
