# Только бэкенд; фронт собирается из frontend/Dockerfile.
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY pytest.ini ./

ENV DB_PATH=/srv/data/attendance.db
# 0.0.0.0 - чтобы порт был виден снаружи контейнера; наружу его отдаёт compose.
ENV API_HOST=0.0.0.0 API_PORT=8000
VOLUME ["/srv/data"]
EXPOSE 8000

CMD ["python", "-m", "app.cli", "serve"]
