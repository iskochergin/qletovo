# Развёртывание на сервере (systemd + nginx + HTTPS)

Инструкция для чистого Ubuntu/Debian-сервера. Запускаем как нативный сервис `qletovo`
(без Docker) за nginx с HTTPS. Домен в примере — **qletovo.kochergin.me** (замени на свой,
если другой).

Нужно: сервер с публичным IP, домен (A-запись на IP), ключ OpenAI (`sk-...`).

---

## 1. Системные пакеты

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git nginx certbot python3-certbot-nginx \
                    tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng
```

`tesseract-*` — для OCR сканированных PDF при индексации.

---

## 2. Пользователь и код

Отдельный системный пользователь `qletovo` и код в `/opt/qletovo`:

```bash
sudo useradd --system --create-home --home-dir /opt/qletovo --shell /usr/sbin/nologin qletovo
sudo -u qletovo git clone https://github.com/iskochergin/qletovo.git /opt/qletovo
cd /opt/qletovo
```

> Приватный репозиторий — настрой deploy-key для пользователя `qletovo` или клонируй по SSH.

---

## 3. venv и зависимости

```bash
sudo -u qletovo python3 -m venv /opt/qletovo/.venv
sudo -u qletovo /opt/qletovo/.venv/bin/pip install --upgrade pip
sudo -u qletovo /opt/qletovo/.venv/bin/pip install -r /opt/qletovo/requirements.txt
```

---

## 4. .env

```bash
sudo -u qletovo cp /opt/qletovo/.env.example /opt/qletovo/.env
sudo -u qletovo nano /opt/qletovo/.env
```

Заполнить:
- `OPENAI_API_KEY=sk-...` — ключ.
- `ADMIN_PASSWORD=...` — свой пароль для `/admin`.
- `OPENAI_BASE_URL=` — пусто, если `api.openai.com` доступен; иначе URL прокси (актуально для РФ).
- `PUBLIC_BASE_URL=` — оставить **пустым** (домен берётся из запроса автоматически).

Защитить файл с секретами:
```bash
sudo chmod 600 /opt/qletovo/.env && sudo chown qletovo:qletovo /opt/qletovo/.env
```

---

## 5. Собрать индекс

```bash
sudo -u qletovo /opt/qletovo/.venv/bin/python -m scripts.reindex
```
~5–10 мин (OCR сканов). В конце выведет `{"documents": ..., "chunks": ...}`.

---

## 6. systemd-сервис `qletovo`

Unit уже в репозитории — `deploy/qletovo.service` (слушает `127.0.0.1:8765`, наружу — nginx):

```bash
sudo cp /opt/qletovo/deploy/qletovo.service /etc/systemd/system/qletovo.service
sudo systemctl daemon-reload
sudo systemctl enable --now qletovo
```

Проверка:
```bash
systemctl status qletovo          # active (running)
journalctl -u qletovo -f          # логи: стартовый баннер + вопросы + вызовы OpenAI
curl -s http://127.0.0.1:8765/health
```

---

## 7. nginx + HTTPS для qletovo.kochergin.me

Конфиг `/etc/nginx/sites-available/qletovo`:
```nginx
server {
    listen 80;
    server_name qletovo.kochergin.me;

    client_max_body_size 50m;     # загрузка крупных PDF через /admin

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;                  # домен в ссылках на PDF
        proxy_set_header X-Forwarded-Proto $scheme;   # https в ссылках
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_read_timeout 60s;                       # ответ LLM до ~20с
    }
}
```

Включить и выпустить сертификат:
```bash
sudo ln -s /etc/nginx/sites-available/qletovo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d qletovo.kochergin.me     # HTTPS + редирект http→https
```

Готово:
- чат — **https://qletovo.kochergin.me**
- админка — **https://qletovo.kochergin.me/admin** (пароль = `ADMIN_PASSWORD`)

---

## 8. Обновление кода

```bash
cd /opt/qletovo
sudo -u qletovo git pull
sudo -u qletovo /opt/qletovo/.venv/bin/pip install -r requirements.txt   # если менялись зависимости
sudo -u qletovo /opt/qletovo/.venv/bin/python -m scripts.reindex          # если менялись документы/индексатор
sudo systemctl restart qletovo
```

---

## 9. Эксплуатация

```bash
sudo systemctl restart qletovo     # перезапуск
sudo systemctl stop qletovo        # остановить
journalctl -u qletovo -f           # живые логи (вопросы, вызовы OpenAI, время)
journalctl -u qletovo --since "1 hour ago"
```

**Документы:** добавляются через `/admin` (загрузка PDF, авто-индексация с OCR) — перезапуск не нужен.
**Бэкап:** сохранить `data/docs/` (PDF) и `.env`. Индекс `data/index/` пересобирается `scripts.reindex`.

---

## Частые проблемы

| Симптом | Решение |
|---|---|
| `502 Bad Gateway` | Сервис не запущен: `systemctl status qletovo`, `journalctl -u qletovo -n 50`. |
| «Сервис временно недоступен» в ответах | Сервер не достучался до OpenAI. Проверь `OPENAI_API_KEY` и доступность `api.openai.com` (РФ → `OPENAI_BASE_URL` на прокси). |
| Ссылки на PDF ведут на `127.0.0.1` | nginx не пробрасывает `Host`/`X-Forwarded-Proto` — добавь `proxy_set_header` (шаг 7). |
| `/admin` не пускает | Неверный `ADMIN_PASSWORD`; после правки `.env` → `sudo systemctl restart qletovo`. |
| `413 Request Entity Too Large` | Увеличь `client_max_body_size` в nginx. |
| Изменения кода не применились | Забыл `sudo systemctl restart qletovo` после `git pull`. |

---

> Docker-вариант (compose) тоже поддерживается — см. `docker-compose.yml` и `Dockerfile`,
> но для одного сервера systemd-способ выше проще и легче.
