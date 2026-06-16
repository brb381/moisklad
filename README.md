# MoySklad Gross Turnover Reports API

FastAPI-сервис для генерации Excel-отчетов о валовом обороте по данным МойСклад.

## Stack

- Python
- FastAPI
- SQLite
- httpx
- openpyxl

## Safety

- МойСклад-клиент разрешает только `GET`.
- `POST`, `PUT`, `PATCH`, `DELETE` к МойСклад запрещены кодом.
- Токен читается только из локального `.env`.
- `.env`, `jobs.sqlite3`, `generated/` не коммитятся.

## Run

Создать `.env`:

```env
MOYSKLAD_TOKEN=...
DATA_SOURCE=moysklad
REPORT_WORKERS=1
MOYSKLAD_MAX_CONCURRENT_REQUESTS=2
MOYSKLAD_MIN_REQUEST_INTERVAL_SECONDS=0.25
MOYSKLAD_RETRY_ATTEMPTS=3
MOYSKLAD_RETRY_BASE_DELAY_SECONDS=1.0
REPORT_RESULT_TTL_SECONDS=3600
```

Запуск:

```bat
run_api.bat
```

URL:

```text
http://127.0.0.1:8010
```

## Stores

Магазины настраиваются в `stores.json`.

Проверенная точка:

```text
planeta -> bcbff9c3-79c4-11f0-0a80-05d4001f0e49
```

Получить точки из МойСклад:

```bat
diagnose_moysklad.bat
```

или:

```http
GET /moysklad/stores
```

## API

```http
GET /health
GET /stores
GET /months
GET /months?months_back=36
```

Создать отчет:

```http
POST /reports/gross-turnover
Content-Type: application/json

{
  "store": "planeta",
  "month": "2026-05",
  "source": "moysklad"
}
```

Статус:

```http
GET /reports/jobs/{job_id}
```

Скачать:

```http
GET /reports/jobs/{job_id}/download
```

Синхронная проверка:

```http
GET /reports/gross-turnover?store=planeta&month=2026-05&source=moysklad
```

## Jobs

Задачи хранятся в `jobs.sqlite3`.

Dedup key:

```text
store + month + source
```

TTL готового отчета:

```text
REPORT_RESULT_TTL_SECONDS=3600
```

Правила:

- `queued` / `processing` возвращают существующий `job_id`.
- `done` младше TTL возвращает существующий `job_id`.
- `done` старше TTL пересоздается.
- `failed` пересоздается.

## Files

Шаблоны:

```text
templates/
```

Готовые отчеты:

```text
generated/
```

Проверенный отчет `planeta / 2026-05`:

```text
Оборот: 848 864.70
Чеки: 559
Товарные позиции: 559
```
