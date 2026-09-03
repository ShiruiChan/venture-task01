# Деплой

Сервер и фронт - два отдельных сервиса. Бэкенд (FastAPI) отдаёт только JSON,
дашборд (Nuxt 4) собирается в статику и раздаётся своим процессом. Поднимаются
по отдельности, порядок не важен.

| Сервис | Порт | Что отдаёт |
|---|---|---|
| `api` | 8000 | `/api/*` - JSON, `/health` - проверка, `/docs` - Swagger, `/` - паспорт сервиса |
| `web` | 3000 | дашборд на Nuxt + прокси `/api` в сервис `api` |

## Эндпоинты API

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/health` | статус, диапазон накопленных данных, режим счётчиков |
| GET | `/api/meta` | пресеты периодов, названия источников и статусов, пороги |
| GET | `/api/divisions` | список подразделений |
| GET | `/api/comparison` | сверка по периоду: `preset`, `date_from`, `date_to`, `division_id` |
| GET | `/api/discrepancies` | только проблемные сутки, отсортированы по тяжести |
| GET | `/api/sources` | сопоставление объектов источников, подразделения, история запусков |
| POST | `/api/mapping` | переназначить объект источника: `{source, external_id, division_id}` |
| POST | `/api/sync` | ручной сбор: `?days=N` |
| GET | `/api/rarus/hourly` | почасовая детализация 1С-Рарус: `?day=ГГГГ-ММ-ДД` |
| GET | `/api/runs` | журнал запусков сбора: `?limit=N` |

## Вариант 1. Docker (рекомендуемый)

```bash
./deploy.sh          # оба сервиса
./deploy.sh api      # только сервер
./deploy.sh web      # только фронт
```

То же напрямую через compose:

```bash
docker compose up -d --build api
docker compose up -d --build web
```

`.env` подключается к сервису `api` через `env_file`, база лежит в `./data`
(переживает пересборку). Образ сам выставляет `API_HOST=0.0.0.0`.

Фронт ходит на относительный `/api`, nginx внутри контейнера `web` проксирует
его в `api:8000` (`frontend/nginx.conf`). Origin один, CORS не участвует.
Адрес резолвится в момент запроса, так что `web` поднимается и без `api`:
до его старта `/api` отвечает 502, статика отдаётся как обычно.

Обновление после правок - та же команда. Логи: `docker compose logs -f api`.
Остановить один сервис: `docker compose stop web`.

Счётчики (`LASER_COUNTERS`) и 1С-Рарус (`RARUS_BASE_URL`) - адреса локальной
сети, контейнер `api` должен стоять в том же контуре. На Linux при проблемах
с доступом к счётчикам заменить в `docker-compose.yml` проброс портов на
`network_mode: host`.

## Вариант 2. Фронт на внешнем хостинге

На Vercel/Netlify/GitHub Pages прокси из варианта 1 нет - браузер ходит на API
напрямую, и адрес вшивается в сборку:

```bash
API_URL=https://api.example.com/api ./deploy.sh static
```

Статика окажется в `frontend/.output/public`. Серверу нужен публичный адрес
и разрешённый источник:

```
CORS_ORIGINS=https://dashboard.example.com
```

Несколько доменов - через запятую. Если домены заранее не известны
(превью-деплои), есть `CORS_ORIGIN_REGEX`, например `https://.*\.vercel\.app`.

### Vercel (через git-интеграцию)

В корне лежит `vercel.json`: Vercel собирает только фронт и раздаёт статику,
Python-функция не создаётся.

```json
"buildCommand": "NUXT_APP_BASE_URL=/ NITRO_PRESET=static npm --prefix frontend run generate",
"outputDirectory": "frontend/.output/public"
```

**`NITRO_PRESET=static` задан явно:** иначе Nitro видит переменную `VERCEL=1`,
сам переключается на пресет `vercel` и кладёт сборку в `.vercel/output` вместо
`.output/public`.

В настройках проекта Vercel нужна одна переменная - **на этапе Build**, потому
что адрес API вшивается в статику при сборке, а не читается в браузере:

| Переменная | Значение |
|---|---|
| `NUXT_PUBLIC_API_BASE` | `https://<адрес-сервера>/api` |

Без неё подставится `/api`, и фронт будет стучаться на сам домен Vercel - 404.

**Сервер на Vercel не поднять.** `LASER_COUNTERS` и `RARUS_BASE_URL` - адреса
локальной сети, из дата-центра Vercel недоступны; SQLite нужен постоянный том,
а автосбору (`AUTOSYNC`) - живой процесс с планировщиком. Сервер остаётся на
варианте 1 или 3.

## Вариант 3. Без Docker, на хосте

Сервер:

```bash
./deploy.sh local
# или напрямую
.venv/bin/python -m app.cli serve --host 0.0.0.0 --port 8000
```

Для постоянной работы - systemd-юнит:

```
ExecStart=/srv/venture-task01/.venv/bin/python -m app.cli serve
EnvironmentFile=/srv/venture-task01/.env
```

Фронт в разработке проксирует `/api` на сервер:

```bash
cd frontend && npm install && npm run dev      # http://localhost:3000
BACKEND_URL=http://192.168.0.10:8000/api npm run dev   # сервер на другой машине
```

## Переменные сети

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `API_HOST` | `127.0.0.1` (в Docker `0.0.0.0`) | интерфейс, на котором слушает сервер |
| `API_PORT` | `8000` | порт сервера |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | домены фронта; `*` - любой источник |
| `CORS_ORIGIN_REGEX` | пусто | шаблон доменов, когда список заранее не известен |
| `NUXT_PUBLIC_API_BASE` | `/api` | адрес API, вшивается в сборку фронта |
| `NUXT_PUBLIC_REFRESH_MINUTES` | `10` | шаг автообновления дашборда; `0` - только кнопка вручную |
| `BACKEND_URL` | `http://127.0.0.1:8000/api` | куда `nuxt dev` проксирует `/api` |

## Автообновление статистики

Два независимых цикла с шагом 10 минут:

* сервер собирает данные из 1С-Рарус и счётчиков планировщиком APScheduler:
  `AUTOSYNC=1`, шаг `SYNC_INTERVAL_MINUTES=10`, глубина `SYNC_LOOKBACK_DAYS`;
  первый сбор - сразу при старте;
* дашборд перезапрашивает `/api/comparison` тем же шагом
  (`NUXT_PUBLIC_REFRESH_MINUTES=10`) и показывает время последнего обновления
  в панели периода. На скрытой вкладке таймер стоит, при возврате данные
  подтягиваются сразу.

Шаг фронта вшивается в сборку: для Docker - build-arg
`NUXT_PUBLIC_REFRESH_MINUTES`, для Vercel - переменная окружения на этапе Build.

## Примечания

* `.env` содержит пароли к 1С и счётчикам - он в `.gitignore`, в git его класть
  нельзя. На сервере разложить руками или через секреты CI.
* Серверные страницы на Jinja2/HTMX (`/`, `/division/{id}`, `/sources`) и каталог
  `app/static` удалены вместе с `app/charts.py`: шаблонов в репозитории не было,
  роуты отвечали 500, весь UI живёт в Nuxt. Их данные доступны через
  `/api/sources`, `/api/comparison` и `/api/meta`.
