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
# заполните OPENAI_API_KEY, TELEGRAM_TOKEN, ADMIN_PASSWORD, PUBLIC_BASE_URL
```

LLM и эмбеддинги — **OpenAI (ChatGPT) API**:
- `OPENAI_API_KEY` — ключ (sk-…) с https://platform.openai.com/api-keys;
- `OPENAI_MODEL` — чат-модель ответов (по умолчанию `gpt-4o-mini`);
- `OPENAI_EMBED_MODEL` — модель эмбеддингов (по умолчанию `text-embedding-3-small`, 1536-dim);
- `OPENAI_BASE_URL` — пусто = `api.openai.com`; задайте для OpenAI-совместимого прокси.

При смене модели эмбеддингов индекс нужно пересобрать (`python -m scripts.reindex`).

## Сборка индекса

```bash
python -m scripts.reindex          # пересобрать индекс из всех PDF в data/docs
```

Учебные программы (ООП, рабочие программы — объёмные педагогические документы на тысячи
страниц) по умолчанию НЕ индексируются: они засоряют поиск по нормативным вопросам (приём,
правила, оценивание, политики). Это управляется `INDEX_EXCLUDE` (regex по имени файла) в `.env`.
Чтобы включить их в индекс, очистите `INDEX_EXCLUDE`. Прунинг уже собранного индекса без
пересчёта эмбеддингов: `python -c "from app.indexer import prune_index; print(prune_index())"`.

## Запуск бэкенда

```bash
python -m app.server               # http://127.0.0.1:8765
```

- Веб-чат:  `http://127.0.0.1:8765/`
- Админка:  `http://127.0.0.1:8765/admin`  (пароль = `ADMIN_PASSWORD`)
- API:      `POST /query {"question": "...", "history": [{"role","content"}]}` → `{answer, sources:[{title,page,url}], status, text}`
- Документы: `GET /manifest`
- PDF:      `GET /files/<имя>.pdf#page=N`

**Память диалога.** Поле `history` в `/query` даёт память диалога — короткие уточнения вроде
«а разве не 8 баллов?» работают в контексте предыдущих вопросов (фронт шлёт последние реплики).

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

### Headless-краулер для letovo.ru (SPA)

`letovo.ru` — client-side SPA: ссылки на PDF подставляются JavaScript-ом (файлы под `/storage/`),
поэтому статический краулер их не видит. Для него есть headless-вариант на Playwright:

```bash
pip install -r requirements-crawl.txt
python -m playwright install chromium
# страница «Сведения об образовательной организации» — реестр всех документов школы (~277 PDF):
python -m app.crawl_js --pages https://letovo.ru/o-shkole/svedenia-ob-obrazovatelnoy-organizacii
python -m app.crawl_js          # или обойти все страницы из sitemap.xml
python -m scripts.reindex       # затем пересобрать индекс
```

### Регидратация корпуса

Тяжёлый набор PDF в git не хранится (сотни МБ), но `data/docs/_sources.json` (карта файл → URL)
закоммичен. Восстановить корпус на новой машине без браузера:

```bash
python -m scripts.fetch_sources    # скачает все PDF из _sources.json
python -m scripts.reindex
```

## Админка

`/admin` (пароль из `.env`): загрузка PDF (с авто-индексацией), полная переиндексация,
список документов, удаление. Загруженный PDF сразу появляется в ответах.

## Проверка метрик (eval)

```bash
python -m eval.run                 # in-process
python -m eval.run --api http://127.0.0.1:8765   # через HTTP
```

Целевые метрики (раздел 5 ТЗ) и достигнутые на контрольном наборе из 18 вопросов
(корпус — 147 нормативных PDF; OpenAI gpt-4o-mini + text-embedding-3-small):

| Метрика | Цель | Факт |
|---|---|---|
| Точность ответов | ≥ 85% | **94%** |
| Доля ответов с валидной ссылкой на страницу | ≥ 95% | **100%** |
| Средняя задержка ответа | ≤ 20 c | **~6.5 c** |
| Галлюцинации на вопросах без данных | 0 | **0** |

## Деплой

### Docker Compose (рекомендуется)

```bash
cp .env.example .env          # заполнить ключи (OPENAI_API_KEY и т.д.)
# положить PDF в ./data/docs (краулером или scripts/fetch_sources.py)
docker compose build
docker compose run --rm api python -m scripts.reindex   # разовая сборка индекса
docker compose up -d           # поднимет api (8765) и bot
```

`./data` смонтирован томом (PDF + индекс переживают пересборку образа). Бот ходит к API по
имени сервиса (`http://api:8765`). Перед публичным доступом поставьте reverse-proxy (nginx)
с TLS на порт 8765.

### Домен и ссылки на PDF

Ссылки на документы (`#page=N`) **не привязаны к домену**: по умолчанию (`PUBLIC_BASE_URL`
пуст) берётся домен из запроса. На любом домене всё заработает само — нужно лишь, чтобы nginx
передавал заголовки:

```nginx
location / {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Задавайте `PUBLIC_BASE_URL=https://ваш-домен` в `.env` **только** если используете Telegram-бот
(он обращается к бэкенду по внутреннему адресу, поэтому ему нужен явный публичный домен для
кнопок-ссылок) или хотите зафиксировать канонический домен.

### systemd (без Docker)

Юниты — в `deploy/`. Предполагается код в `/opt/qletovo`, venv в `/opt/qletovo/.venv`,
пользователь `qletovo`.

```bash
sudo cp deploy/qletovo-api.service deploy/qletovo-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qletovo-api qletovo-bot
```

API слушает `0.0.0.0:8765` (за nginx/TLS), бот — отдельный сервис, зависит от API.

## Известные ограничения

- Модель ответов задаётся в `.env` (`OPENAI_MODEL`): `gpt-4o-mini` — дёшево и качественно;
  для сложных формулировок можно поставить `gpt-4o`.
- Краулер не делает OCR: PDF-сканы без текстового слоя не индексируются (в корпусе letovo.ru
  таких ~47 — для них нужен OCR-шаг).
- Релевантностный гейт (`OFFTOPIC_GATE`) отсекает посторонние вопросы до обращения к LLM.
  Порог зависит от модели эмбеддингов — для `text-embedding-3-small` его нужно
  откалибровать после первой реиндексации (замерить top-сходство для вопросов «по теме»
  и «вне темы»).
