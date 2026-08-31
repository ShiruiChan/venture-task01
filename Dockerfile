# --- 1. Сборка Nuxt в статику -------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# baseURL совпадает с FRONTEND_MOUNT у FastAPI; API — на том же origin.
ENV NUXT_APP_BASE_URL=/app/
ENV NUXT_PUBLIC_API_BASE=/api
RUN npm run generate

# --- 2. Рантайм: FastAPI + собранный фронт ------------------------------------
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY pytest.ini ./
COPY --from=frontend /build/.output/public ./frontend/.output/public

ENV DB_PATH=/srv/data/attendance.db
VOLUME ["/srv/data"]
EXPOSE 8000

CMD ["uvicorn", "app.web:app", "--host", "0.0.0.0", "--port", "8000"]
