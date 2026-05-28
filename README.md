# Ассистент школы «Летово» — RAG по официальным документам

ИИ-ассистент, который отвечает на вопросы **только** по официальным PDF-документам школы
и **всегда** даёт ссылку на конкретную страницу первоисточника (`.../doc.pdf#page=N`).
Один бэкенд обслуживает два клиента: **веб-чат** (чёрно-белый минимализм) и **Telegram-бот**.

Если ответа в документах нет — ассистент честно отвечает
«В документах школы нет данных по этому вопросу.» и ничего не выдумывает. На посторонние
вопросы (код, общие знания, личные советы) — вежливо отказывается.

## Архитектура

```
[ Веб-чат (frontend/chat.html) ]      [ Telegram-бот (telegram/bot.py) ]
              │                                      │
              └──────────────────┬───────────────────┘
                                 ▼
                     Backend API — FastAPI (app/)
            POST /query · GET /manifest · /admin* (пароль)
                                 │
        ┌────────────────────────┼─────────────────────────┐
        ▼                        ▼                          ▼
   Ingestion (app/ingest)   Vector store (app/store)   LLM (app/llm)
   PyMuPDF, постранично     numpy flat-cosine,         Yandex (default)
                            инкрементальный            | OpenAI-совместимый
                                 ▲
                            Embeddings (app/embeddings) — Yandex 256-dim
```

## Структура

```
app/            бэкенд: config, embeddings, llm, store, ingest, indexer, rag, crawl, server
frontend/       chat.html (Ч/Б чат) + admin.html (админка с паролем)
telegram/       bot.py + config.py (Telegram-бот на общем /query)
data/docs/      PDF-документы (источники)
data/index/     индекс: chunks.json, vectors.npy, manifest.json (пересобираемый)
eval/           questions.yaml + run.py (проверка метрик)
scripts/        reindex.py (CLI полной пересборки индекса)
.env.example    шаблон конфигурации
PLAN.md         архитектура и план
MIGRATION_NOTES.md  что удалено / переписано / сохранено
```

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Совет: если проект лежит в синхронизируемой папке (Yandex.Disk / Dropbox), которая
> сбрасывает признак исполняемости с бинарников venv, создайте окружение вне папки проекта:
> `python3 -m venv ~/.cache/qletovo-venv` и используйте `~/.cache/qletovo-venv/bin/python`.

## Настройка

```bash
cp .env.example .env
# заполните YANDEX_FOLDER_ID, YANDEX_API_KEY, TELEGRAM_TOKEN, ADMIN_PASSWORD, PUBLIC_BASE_URL
```

LLM по умолчанию — **Yandex Cloud** (`yandexgpt-lite` + эмбеддинги 256-dim, RU-инфраструктура).
Чтобы переключиться на любой OpenAI-совместимый провайдер: `LLM_PROVIDER=openai` и заполните
`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`.

## Сборка индекса

```bash
python -m scripts.reindex          # пересобрать индекс из всех PDF в data/docs
```

## Запуск бэкенда

```bash
python -m app.server               # http://127.0.0.1:8765
```

- Веб-чат:  `http://127.0.0.1:8765/`
- Админка:  `http://127.0.0.1:8765/admin`  (пароль = `ADMIN_PASSWORD`)
- API:      `POST /query {"question": "..."}` → `{answer, sources:[{title,page,url}], status, text}`
- Документы: `GET /manifest`
- PDF:      `GET /files/<имя>.pdf#page=N`

## Telegram-бот

Бот ходит на общий бэкенд (`BACKEND_URL` → `/query`), поэтому ответы идентичны вебу.

```bash
python -m telegram.bot             # бэкенд должен быть запущен
```

Команды: `/start`, `/help`, `/docs`. Есть анти-спам (5 c) и дневной лимит (30 запросов).

## Краулер (сбор PDF с сайта)

```bash
python -m app.crawl                       # обходит letovo.ru / qletovo.ru
python -m app.crawl --no-verify           # если у qletovo.ru self-signed TLS
python -m app.crawl --max-pages 200 --delay 1.0
python -m app.crawl --no-sitemap          # без засева из sitemap.xml
```

Вежливый (rate-limit, robots.txt), засевается из `sitemap.xml`, скачивает PDF в `data/docs/`,
дедуп по sha1, метаданные (source_url) → `data/docs/_sources.json`. После краулинга запустите
`python -m scripts.reindex`.

> **Важно про letovo.ru.** Сайт — client-side SPA: в исходном HTML ссылок почти нет (даже на
> странице «Сведения об образовательной организации» ссылки на PDF подставляются JavaScript-ом),
> а файлы лежат под `/storage/`. Статический краулер их не видит. Варианты сбора PDF:
> (1) залить документы вручную через `/admin`; (2) указать прямые URL из `/storage/`;
> (3) добавить headless-рендеринг (Playwright) — задел оставлен, но в текущую сборку не входит.
> Стартовый набор из 3 нормативных PDF уже лежит в `data/docs/` и проиндексирован.

## Админка

`/admin` (пароль из `.env`): загрузка PDF (с авто-индексацией), полная переиндексация,
список документов, удаление. Загруженный PDF сразу появляется в ответах.

## Проверка метрик (eval)

```bash
python -m eval.run                 # in-process
python -m eval.run --api http://127.0.0.1:8765   # через HTTP
```

Целевые метрики (раздел 5 ТЗ) и достигнутые на контрольном наборе из 17 вопросов:

| Метрика | Цель | Факт |
|---|---|---|
| Точность ответов | ≥ 85% | **100%** |
| Доля ответов с валидной ссылкой на страницу | ≥ 95% | **100%** |
| Средняя задержка ответа | ≤ 20 c | **~2 c** |
| Галлюцинации на вопросах без данных | 0 | **0** |

## Известные ограничения

- `yandexgpt-lite` — лёгкая модель; на сложных формулировках качество ниже, чем у полной
  `yandexgpt`. Модель и провайдер меняются через `.env` без изменения кода.
- Краулер не делает OCR: PDF-сканы без текстового слоя не индексируются.
- Релевантностный гейт (`OFFTOPIC_GATE`, по умолчанию 0.30) отсекает явно посторонние
  вопросы до обращения к LLM; при смене модели эмбеддингов порог стоит перепроверить.
