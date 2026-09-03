#!/usr/bin/env bash
# Режимы: all | api | web | static | local (подробнее - DEPLOY.md).
set -euo pipefail
cd "$(dirname "$0")"

mode="${1:-all}"

need_env() { [ -f .env ] || { echo "Нет .env - скопируйте настройки перед деплоем"; exit 1; }; }

case "$mode" in
  all)
    need_env
    docker compose up -d --build
    echo "Готово: дашборд http://localhost:3000/ , API http://localhost:8000/api"
    ;;

  api)
    need_env
    docker compose up -d --build api
    echo "Готово: API http://localhost:8000/api , проверка http://localhost:8000/health"
    ;;

  web)
    docker compose up -d --build web
    echo "Готово: дашборд http://localhost:3000/"
    ;;

  static)
    # Статика под внешний хостинг; сервер остаётся здесь.
    : "${API_URL:?Задайте публичный адрес API, например: API_URL=https://api.example.com/api ./deploy.sh static}"
    cd frontend
    npm ci
    NUXT_APP_BASE_URL=/ NUXT_PUBLIC_API_BASE="$API_URL" npm run generate
    echo "Готово: выложите frontend/.output/public на хостинг."
    echo "На сервере задайте CORS_ORIGINS=<домен фронта>, иначе браузер заблокирует запросы."
    ;;

  local)
    need_env
    exec .venv/bin/python -m app.cli serve --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
    ;;

  *)
    echo "Неизвестный режим: $mode (all | api | web | static | local)"; exit 1
    ;;
esac
