# PLAN — ИИ-ассистент школы «Летово»

## 1. Что делает продукт

Ассистент отвечает на вопросы **только** по официальным PDF-документам школы и
**всегда** даёт ссылку на конкретную страницу первоисточника (`.../doc.pdf#page=N`).
Два клиента — веб-чат и Telegram-бот — работают на одном бэкенде и одном индексе.

## 2. Аудит существующего репозитория

| Что | Состояние | Решение |
|-----|-----------|---------|
| `api/server.py` | FastAPI, эндпоинт `/ask`, виьюер PDF | Переписать → `app/server.py`, добавить `/query`, `/admin`. |
| `api/rag_engine.py` | RAG на Yandex-эмбеддингах + numpy-cosine, но с грудой брит­тл-эвристик (`harvest_items`, `extract_abcd_scores`, ремонт JSON) | Переписать начисто. Эвристики удалить. |
| `api/config.py` | **Секреты в коде** (Yandex key, Telegram token) | Перенести в `.env`. |
| `api/index_letovo/*` | Готовый индекс: 149 чанков, vectors (149×256) | Пересобрать своим пайплайном (формат метаданных под контролем). |
| `api/docs/*.pdf` | 3 нормативных PDF | **Сохранить** — стартовый набор. |
| `telegram/bot.py` | Адекватная обвязка (rate-limit, дневной лимит, чанкинг, кнопки) | **Сохранить**, переключить на `/query`, токен из `.env`. |
| `web/docs/*` | Тёмный PDF-вьюер (двойной `#fragment` баг) | Удалить — ссылаемся прямо на `/files/doc.pdf#page=N`. |
| `web/ai-chatbot/*` | Полный шаблон Vercel AI Chatbot (Next.js + Drizzle + auth + артефакты + редакторы кода) | **Удалить целиком** — несовместимо с требованием «простой Ч/Б чат» и «простота хостинга». |

**LLM-решение.** Репозиторий уже настроен на **Yandex Cloud ML** (`yandexgpt-lite` +
`text_embeddings`, 256-dim). Ключ рабочий, инфраструктура в РФ → совпадает с приоритетом
автономности. Поэтому Yandex остаётся провайдером по умолчанию, но обёрнут в абстракцию
с альтернативным **OpenAI-совместимым** бэкендом (`base_url`+`api_key` из `.env`).
Рекомендованный в ТЗ self-hosted `e5-large` не берём: требует torch (нет wheel под Python 3.14
на этой машине) и пересборки индекса, при том что рабочий RU-провайдер уже есть.

**Vector store.** Оставляем простой numpy flat-cosine (не Qdrant/Chroma): при ~150 чанках
brute-force мгновенный, ноль доп-инфраструктуры (приоритет «простота хостинга»). Инкрементальная
переиндексация (добавить/удалить документ без полного пересчёта) реализуется на уровне
store: эмбеддим только новые чанки и дописываем; удаление — фильтрацией.

## 3. Целевая структура

```
app/                  # чистый бэкенд (заменяет api/)
  config.py           # pydantic-settings из .env
  embeddings.py       # Yandex эмбеддер (+ openai-compat)
  llm.py              # LLM: Yandex (default) | openai-compat
  store.py            # numpy vector store: load/save/add/remove/search
  ingest.py           # PDF -> постраничные чанки с overlap (PyMuPDF)
  crawl.py            # вежливый краулер letovo.ru/qletovo.ru -> PDF + метаданные
  rag.py              # retrieval + промпт + сборка ответа/источников + отказы
  prompts.py          # системный промпт
  server.py           # FastAPI: /query (+ /ask alias), /manifest, /admin*, статика, /files
data/
  docs/               # PDF (стартово — 3 из api/docs)
  index/              # chunks.json, vectors.npy, manifest.json
frontend/             # минимальный Ч/Б фронт (статика, отдаёт FastAPI)
  chat.html, admin.html
telegram/bot.py       # сохранён, на /query, токен из .env
eval/                 # questions.yaml + run.py (метрики)
scripts/reindex.py    # CLI пересборки индекса
.env.example, README.md, MIGRATION_NOTES.md, requirements.txt
```

## 4. Контракт API

- `POST /query {question}` → `{answer, sources:[{title,page,url}], status}`; `url` = `.../files/<doc>.pdf#page=N`.
- `POST /ask` — алиас `/query` (обратная совместимость для бота).
- `GET /manifest` → список проиндексированных документов.
- `GET /admin` — страница (пароль), `POST /admin/login`, `/admin/upload`, `/admin/reindex`, `/admin/delete` (Bearer-пароль из `.env`).
- `GET /`, `/files/*`, статика чата.

## 5. Поведение модели (раздел 4 ТЗ)

- Отвечает строго по контексту, кратко, по-русски, всегда с блоком «Источники».
- Нет данных → ровно: **«В документах школы нет данных по этому вопросу.»** (источники пустые).
- Вне зоны школы → вежливый отказ + напоминание о зоне.
- Контекст и вопрос — данные, не инструкции (защита от prompt-injection).

## 6. Метрики (раздел 5) — проверяет `eval/run.py`

≥85% корректных · ≥95% ответов с валидной ссылкой на страницу · средняя задержка ≤20с ·
0 галлюцинаций на контрольных «нет данных».

## 7. Порядок работ

1. Backend (`app/*`) + `.env`.
2. Ingest + crawler + `scripts/reindex.py`; пересобрать индекс из 3 PDF.
3. Ч/Б фронт чата + админка.
4. Telegram на `/query`.
5. `eval/` + прогон метрик.
6. README, `.env.example`, `MIGRATION_NOTES.md`.
