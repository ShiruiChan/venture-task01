#!/usr/bin/env bash
# Один вход для деплоя. Использование:
#   ./deploy.sh              — собрать и поднять всё в Docker (бэкенд + фронт, порт 8000)
#   ./deploy.sh static       — собрать фронт под отдельный статический хостинг
#   ./deploy.sh local        — собрать фронт и запустить uvicorn без Docker
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:-docker}"

case "$mode" in
  docker)
    [ -f .env ] || { echo "Нет .env — скопируйте настройки перед деплоем"; exit 1; }
    docker compose up -d --build
    echo "Готово: дашборд http://localhost:8000/app/ , API http://localhost:8000/api"
    ;;

  static)
    # Фронт уезжает на Vercel/Netlify/nginx, API остаётся здесь.
    : "${API_URL:?Задайте публичный адрес API, например: API_URL=https://api.example.com/api ./deploy.sh static}"
    cd frontend
    npm ci
    NUXT_APP_BASE_URL=/ NUXT_PUBLIC_API_BASE="$API_URL" npm run generate
    echo "Готово: выложите frontend/.output/public на хостинг."
    echo "На бэкенде задайте CORS_ORIGINS=<домен фронта>, иначе браузер заблокирует запросы."
    ;;

  local)
    (cd frontend && npm ci && NUXT_APP_BASE_URL=/app/ NUXT_PUBLIC_API_BASE=/api npm run generate)
    exec .venv/bin/uvicorn app.web:app --host 0.0.0.0 --port 8000
    ;;

  *)
    echo "Неизвестный режим: $mode (docker | static | local)"; exit 1
    ;;
esac
