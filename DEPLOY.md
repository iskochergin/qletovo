# Развёртывание на сервере

Инструкция для чистого Ubuntu/Debian-сервера. Поднимаем ассистента в Docker за nginx с HTTPS.
Всё, что нужно: сервер с публичным IP, домен, ключ OpenAI.

---

## 0. Что понадобится

- VPS/сервер: Ubuntu 22.04+ (≥2 ГБ RAM, ~2 ГБ диска под образ+корпус).
- Домен, нацеленный A-записью на IP сервера (например `letovo-bot.ru`).
- Ключ OpenAI (`sk-...`). Если с сервера не открывается `api.openai.com` (РФ) — нужен
  OpenAI-совместимый прокси (его URL впишем в `OPENAI_BASE_URL`).

---

## 1. Установить Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # чтобы docker без sudo; перелогиниться после
```

Проверка: `docker --version` и `docker compose version`.

---

## 2. Склонировать репозиторий

```bash
sudo mkdir -p /opt && cd /opt
git clone https://github.com/iskochergin/qletovo.git
cd qletovo
```

> Если репозиторий приватный — настрой доступ (deploy key или `gh auth`/токен), либо клонируй по SSH:
> `git clone git@github.com:iskochergin/qletovo.git`.

Корпус PDF и собранный индекс уже в репозитории (`data/docs`, но индекс `data/index`
в .gitignore — соберём в шаге 4).

---

## 3. Настроить .env

```bash
cp .env.example .env
nano .env
```

Обязательно заполнить:
- `OPENAI_API_KEY=sk-...` — твой ключ.
- `ADMIN_PASSWORD=...` — придумай свой надёжный пароль для `/admin`.
- `OPENAI_BASE_URL=` — оставь пустым, если `api.openai.com` доступен; иначе впиши URL прокси.
- `PUBLIC_BASE_URL=` — оставь **пустым** (ссылки на PDF возьмутся из домена запроса автоматически).

Остальное можно не трогать (разумные значения по умолчанию).

---

## 4. Собрать индекс и запустить

```bash
docker compose build
docker compose run --rm api python -m scripts.reindex   # разовая сборка индекса (~5–10 мин, OCR сканов)
docker compose up -d                                    # поднять API на :8765
```

Проверка локально на сервере:
```bash
curl -s http://127.0.0.1:8765/health        # {"ok":true,"documents":...}
docker compose logs -f api                   # логи: видно вызовы OpenAI и вопросы
```

---

## 5. nginx + HTTPS

Установить nginx и certbot:
```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
```

Создать конфиг `/etc/nginx/sites-available/qletovo`:
```nginx
server {
    listen 80;
    server_name letovo-bot.ru;   # ← твой домен

    client_max_body_size 50m;    # чтобы грузить крупные PDF через /admin

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;                       # ← важно: домен в ссылках на PDF
        proxy_set_header X-Forwarded-Proto $scheme;        # ← важно: https в ссылках
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 60s;                            # ответы LLM до ~20с
    }
}
```

Включить и выпустить сертификат:
```bash
sudo ln -s /etc/nginx/sites-available/qletovo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d letovo-bot.ru        # автоматически настроит HTTPS и редирект
```

Готово. Сайт открывается по **https://letovo-bot.ru**, админка — **https://letovo-bot.ru/admin**.
Ссылки на страницы PDF в ответах будут автоматически на твоём домене с https.

---

## 6. Обновление (когда вышли изменения в репозитории)

```bash
cd /opt/qletovo
git pull
docker compose up -d --build        # пересобрать образ со свежим кодом
# если менялись документы/индексатор:
docker compose run --rm api python -m scripts.reindex
docker compose up -d
```

> ВАЖНО: после `git pull` обязательно `--build`, иначе контейнер останется на старом коде.

---

## 7. Эксплуатация

```bash
docker compose ps                 # статус (healthy?)
docker compose logs -f api        # живые логи (вопросы + вызовы OpenAI + время)
docker compose restart api        # перезапуск
docker compose down               # остановить
```

**Бэкап:** достаточно сохранить `data/docs/` (PDF) и `.env`. Индекс `data/index/`
пересобирается командой `scripts.reindex`. Документы, загруженные через `/admin`,
лежат в том же `data/docs/` (том примонтирован) — переживают пересборку образа.

**Добавление документов:** через `/admin` (загрузка PDF, авто-индексация с OCR) — сервер
перезапускать не нужно.

---

## Частые проблемы

| Симптом | Причина / решение |
|---|---|
| Ответы «Сервис временно недоступен» | Сервер не достучался до OpenAI. Проверь `OPENAI_API_KEY` и доступность `api.openai.com` (в РФ — пропиши `OPENAI_BASE_URL` на прокси). `docker compose logs api`. |
| Ссылки на PDF ведут на `127.0.0.1` | nginx не передаёт `Host`/`X-Forwarded-Proto` — добавь `proxy_set_header` (шаг 5). |
| `/admin` не пускает | Неверный `ADMIN_PASSWORD` в `.env`; после правки `.env` → `docker compose up -d`. |
| Изменения кода не применяются | Забыл `--build`: `docker compose up -d --build`. |
| 413 при загрузке PDF | Увеличь `client_max_body_size` в nginx. |
