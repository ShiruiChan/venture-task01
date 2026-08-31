# Деплой

Фронт (Nuxt 4) собирается в статику, FastAPI раздаёт её сам — один процесс, один порт, без CORS.

| Путь | Что отдаёт |
|---|---|
| `/app/` | дашборд на Nuxt |
| `/api/*` | JSON-API |
| `/` , `/division/{id}` , `/sources` | старый Jinja/HTMX-дашборд (сейчас нерабочий, см. «Известные проблемы») |

## Вариант 1. Всё в Docker (рекомендуемый)

```bash
./deploy.sh
```

Собирает Nuxt, ставит Python-зависимости, поднимает `uvicorn` на `:8000`.
`.env` подключается через `env_file`, база лежит в `./data` (том, переживает пересборку).

Обновление после правок — та же команда.
Логи: `docker compose logs -f`. Остановить: `docker compose down`.

**Сеть.** Счётчики (`LASER_COUNTERS`) и 1С-Рарус (`RARUS_BASE_URL`) — адреса локальной сети,
поэтому контейнер должен стоять внутри того же контура. На Linux при проблемах с доступом
к счётчикам заменить в `docker-compose.yml` проброс портов на `network_mode: host`.

## Вариант 2. Фронт на отдельном хостинге

```bash
API_URL=https://api.example.com/api ./deploy.sh static
```

Кладёт готовую статику в `frontend/.output/public` — её можно выложить на Vercel, Netlify,
GitHub Pages или в nginx. Бэкенду при этом нужен публичный адрес и разрешённый источник:

```
CORS_ORIGINS=https://dashboard.example.com
```

(несколько доменов — через запятую; пустое значение = CORS выключен).

### Vercel (через git-интеграцию)

В корне лежит `vercel.json`: Vercel собирает **только фронт** и раздаёт статику,
Python-функция не создаётся.

```json
"buildCommand": "NUXT_APP_BASE_URL=/ NITRO_PRESET=static npm --prefix frontend run generate",
"outputDirectory": "frontend/.output/public"
```

`NITRO_PRESET=static` задан явно: иначе Nitro видит переменную `VERCEL=1`, сам переключается
на пресет `vercel` и кладёт сборку в `.vercel/output` вместо `.output/public`.

В настройках проекта Vercel нужна одна переменная — **на этапе Build**, потому что адрес API
вшивается в статику при сборке, а не читается в браузере:

| Переменная | Значение |
|---|---|
| `NUXT_PUBLIC_API_BASE` | `https://<адрес-бэкенда>/api` |

Без неё `nuxt.config.ts` подставит `/api`, и фронт будет стучаться на сам домен Vercel — 404.

**Бэкенд на Vercel не поднять.** `LASER_COUNTERS` и `RARUS_BASE_URL` — адреса локальной сети,
из дата-центра Vercel они недоступны; плюс SQLite нужен постоянный том, а автосбор
(`AUTOSYNC`) — живой процесс с планировщиком. Бэкенд остаётся на варианте 1 или 3.

## Вариант 3. Без Docker, на хосте

```bash
./deploy.sh local
```

Для постоянной работы — systemd-юнит с `ExecStart=/srv/task1/.venv/bin/uvicorn app.web:app --host 0.0.0.0 --port 8000`.

## Переменные, добавленные для деплоя

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `FRONTEND_DIST` | `frontend/.output/public` | каталог собранного фронта; если его нет — FastAPI просто не монтирует статику |
| `FRONTEND_MOUNT` | `/app` | префикс, по которому отдаётся фронт |
| `CORS_ORIGINS` | пусто | домены фронта, если он живёт отдельно |

`FRONTEND_MOUNT` должен совпадать с `NUXT_APP_BASE_URL` на сборке, иначе не подхватятся ассеты.

## Известные проблемы

* Каталог `app/templates` отсутствует в репозитории, поэтому `/`, `/division/{id}` и `/sources`
  отвечают 500 (`TemplateNotFound`), а три теста в `tests/test_web.py` падают. Либо вернуть шаблоны,
  либо удалить серверные страницы и сделать Nuxt корневым (`FRONTEND_MOUNT=/` + снять роут `/`).
* `.env` содержит пароли к 1С и счётчикам — он в `.gitignore`, в git его класть нельзя.
  На сервере разложить руками или через секреты CI.
