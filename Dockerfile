# Образ обслуживающего бэкенда (FastAPI). Лёгкий: без Playwright/краулера — это ops-инструмент.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8765

WORKDIR /app

# tesseract + рус/англ языки — для OCR сканов при индексации (scripts.reindex в контейнере)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY frontend/ ./frontend/
COPY scripts/ ./scripts/
COPY eval/ ./eval/
COPY media/ ./media/

# Корпус и индекс монтируются томом в /app/data (см. docker-compose.yml).
RUN mkdir -p /app/data/docs /app/data/index

EXPOSE 8765

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers", "--forwarded-allow-ips", "*"]
