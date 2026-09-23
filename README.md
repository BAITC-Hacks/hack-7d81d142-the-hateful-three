# MoneyGraph AI — Граф денег

Локальный инструмент для анализа транзакционного графа и объяснимой приоритизации проверки клиентов по кейсу Freedom на HackAlem AI.

## Что делает продукт

Продукт предназначен для AML-аналитика: по переводам на четыре колена от исходных клиентов он должен определять предполагаемые роли участников и выделять группы связанных узлов. Результат — очередь проверки с числовыми объяснениями и три CSV в формате стартера. Все выводы являются аналитическими гипотезами, которые требуют проверки человеком.

**Текущий статус:** реализованы аудит данных и базовые признаки в `analysis/profile_data.py`, backend с `GET /health`, JWT-аутентификацией по email и защищённым CRUD API для шести сущностей, SQLAlchemy-модели, Pydantic-схемы, репозитории и сервисы, две миграции Alembic для PostgreSQL. Расчёт ролей, кластеров, рейтинга, итоговые выгрузки и интерфейс ещё не реализованы.

## Стек технологий

- **Python** — обработка данных и аналитика.
- **FastAPI, Uvicorn, pydantic-settings** — HTTP-сервер и настройки из окружения и `.env`.
- **PostgreSQL, SQLAlchemy 2, psycopg 3, Alembic** — хранение сущностей и миграции схемы.
- **passlib, bcrypt, PyJWT, email-validator** — хеширование паролей, JWT access-токены и проверка email.
- **pandas, NumPy** — таблицы и расчёт признаков.
- **PyArrow** — чтение Parquet.
- **NetworkX** — направленный взвешенный граф и графовые алгоритмы.
- **Streamlit** — запланированный простой интерфейс после готовности обязательных выгрузок.
- **PyVis** — необязательная визуализация окружения узла, если останется время.

База данных нужна для хранения сущностей; самостоятельный аудит Parquet и health-check работают без подключения к ней. Node.js, внешние API и LLM для текущего MVP не требуются.

## Структура проекта

```text
moneygraph-ai/
├── README.md                    # Описание проекта и команды запуска
├── .gitignore                   # Исключения для Git
├── .env.example                 # Шаблон настроек backend, DATABASE_URL и JWT
├── alembic.ini                  # Конфигурация миграций без паролей
├── alembic/
│   ├── env.py                  # DATABASE_URL и metadata всех моделей
│   └── versions/               # Две миграции: шесть таблиц данных и users
├── analysis/                    # Существующий самостоятельный аудит данных
└── backend/
    ├── __init__.py              # Python-пакет backend
    ├── main.py                  # FastAPI, GET /health, CORS и подключение API
    ├── requirements.txt         # Зависимости HTTP-сервера, ORM и миграций
    ├── requirements-dev.txt     # Зависимости сервера и HTTP-тестов
    ├── api/                    # CRUD-роутеры и заготовки аналитического API
    │   ├── __init__.py          # Общий роутер, собирающий модули
    │   ├── dependencies.py     # get_current_user и сервисы с сессией из get_db
    │   ├── auth.py             # Регистрация, вход по email и текущий пользователь
    │   ├── nodes.py            # CRUD узлов: /nodes/
    │   ├── edges.py            # CRUD рёбер: /edges/
    │   ├── transactions.py     # CRUD транзакций: /transactions/
    │   ├── clusters.py         # CRUD кластеров: /clusters/
    │   ├── node_assessments.py # CRUD оценок: /node-assessments/
    │   ├── ranked_nodes.py     # CRUD записей рейтинга: /ranked-nodes/
    │   ├── dataset.py          # Заготовка сводки датасета: /dataset
    │   ├── analysis.py         # Заготовка запуска анализа: /analysis
    │   ├── ranking.py          # Заготовка очереди проверки: /ranking
    │   ├── graph.py            # Заготовка окружения узла: /graph
    │   └── exports.py          # Заготовка трёх CSV: /exports
    ├── core/
    │   ├── __init__.py
    │   ├── config.py           # Settings: окружение → .env → defaults
    │   ├── database.py         # Engine, фабрика Session и get_db с commit/rollback
    │   ├── logging.py          # Консольные логи и middleware HTTP-запросов
    │   └── security.py         # bcrypt, create_access_token и verify_token
    ├── services/               # CRUD, бизнес-проверки и кастомные исключения
    ├── models/                 # Base, enum ролей, шесть моделей данных и User
    ├── schemas/                # Схемы шести сущностей и аутентификации
    ├── repositories/           # CRUD через SQLAlchemy Session
    └── tests/                  # Проверки миграции, репозиториев, сервисов и HTTP API
```

### HTTP API

Все маршруты данных требуют заголовок `Authorization: Bearer <access_token>`,
включая чтение списков и отдельных объектов. Защищены все операции в `/nodes/`,
`/edges/`, `/transactions/`, `/clusters/`, `/node-assessments/`, `/ranked-nodes/`.
Общий роутер данных подключает `Depends(get_current_user)` также к заготовкам
`/dataset`, `/analysis`, `/ranking`, `/graph`, `/exports`: их будущие обработчики
унаследуют эту проверку.

### Аутентификация

| Метод и путь | Доступ | Результат |
|---|---|---|
| `POST /auth/register` | Публичный | JSON `{ "email": "analyst@example.com", "password": "…" }`; пользователь, `access_token`, `token_type: "bearer"` и `201 Created` |
| `POST /auth/login` | Публичный | Такой же JSON; `{ "access_token": "…", "token_type": "bearer" }` и `200 OK` |
| `GET /auth/me` | Bearer-токен | Текущий пользователь и `200 OK` |

Поля пользователя: `id`, `email`, `created_at`, `updated_at`. Регистрация также
возвращает `access_token` и `token_type`, поэтому защищённые запросы можно выполнять
сразу. `GET /auth/me` возвращает только поля пользователя.
Email проверяется, очищается от пробелов по краям и приводится к нижнему регистру.
Повторная регистрация email возвращает `409`, неверный email или пароль при входе —
`401`, некорректные поля запроса — `422`. В БД хранится уникальный email и
`hashed_password`; пароль и хеш не попадают в ответы API.

Пароль должен содержать минимум 8 символов, занимать не более 72 байт в UTF-8
и не содержать нулевой символ. Для кириллицы и emoji число байт может быть больше
числа символов. Ограничение проверяется до хеширования, чтобы bcrypt не обрезал
пароль: [описание bcrypt в passlib](https://passlib.readthedocs.io/en/stable/lib/passlib.hash.bcrypt.html).

`backend/core/security.py` создаёт и проверяет access-токены с фиксированным
алгоритмом HS256. `get_current_user` — FastAPI dependency: проверяет Bearer-токен
и его срок действия, затем загружает пользователя из БД. Отсутствующий, неверный
или просроченный токен, а также токен удалённого пользователя дают `401` с
`WWW-Authenticate: Bearer`. Проверка подписи и срока действия выполняется через
[PyJWT](https://pyjwt.readthedocs.io/en/stable/usage.html).

Публичны `/auth/register`, `/auth/login`, `/health`, `/docs`, `/redoc`, `/openapi.json`.
Для выдачи и проверки JWT нужен настроенный `JWT_SECRET_KEY`: без него регистрация,
вход с верными данными и попытка проверить Bearer-токен возвращают `503`.
Если токен после регистрации не удалось выдать, создание пользователя откатывается.
Отсутствующий Bearer-заголовок или неверная схема авторизации дают `401`;
неверные данные входа также дают `401`. Health-check, документация и миграции
доступны без JWT-секрета. Клиент передаёт access-токен в `Authorization: Bearer …`;
сам серверный `JWT_SECRET_KEY` не принимается вместо токена.
Данные общие для всех зарегистрированных пользователей; разделение по владельцу
и роли в текущую реализацию не входит. Refresh-токены не выдаются: после истечения
access-токена нужно войти заново.

### Операции с данными

Для `Node`, `Edge`, `Transaction`, `Cluster`, `NodeAssessment`, `RankedNode`
доступны соответственно `/nodes/`, `/edges/`, `/transactions/`, `/clusters/`,
`/node-assessments/`, `/ranked-nodes/`. Каждый роутер поддерживает одинаковые операции:

| Метод | Путь относительно префикса | Результат |
|---|---|---|
| `POST` | `/` | Создание по схеме `Create`, объект и `201 Created` |
| `GET` | `/?skip=0&limit=100` | Список объектов, `200 OK` |
| `GET` | `/{id}` | Один объект, `200 OK` |
| `PATCH` | `/{id}` | Частичное обновление по схеме `Update`, объект и `200 OK` |
| `DELETE` | `/{id}` | Удаление, `204 No Content` без тела ответа |

Например, `GET /nodes/?skip=20&limit=10` возвращает страницу узлов.
`skip` и `limit` — неотрицательные целые числа; `limit=0` возвращает пустой список.
Параметр `{id}` — технический идентификатор записи из ответа API; бизнес-ключи
`gid`, `row_id` и `cluster_id` передаются в полях объекта. `PATCH` меняет только
переданные поля. Отсутствующая запись при чтении, обновлении или удалении даёт `404`.

Роуты вызывают только сервисы. Глобальные обработчики в `backend/main.py`
преобразуют `NotFoundError`, `ConflictError`, `ValidationError` в HTTP `404`, `409`,
`422` соответственно, с телом `{"detail": "описание ошибки"}`. Некорректные
параметры запроса и поля схем возвращают стандартный ответ валидации FastAPI `422`.
Непойманные исключения возвращают `500` с `{"detail": "Internal server error"}`;
полный traceback записывается в серверный лог и не передаётся клиенту.

Стандартный `logging` выводит читаемые консольные сообщения (не JSON).
Middleware записывает каждый HTTP-запрос, включая CORS preflight: метод, путь,
статус и длительность в миллисекундах. Эти значения также доступны как поля
`LogRecord`: `method`, `path`, `status_code`, `duration_ms`. Успешные запросы
и перенаправления имеют уровень `INFO`, ответы `4xx` — `WARNING`, `5xx` — `ERROR`.
В журнал запросов не включаются query string, заголовки и тело запроса.

```text
2026-09-23 12:00:00 | INFO    | backend.access | HTTP request completed | method=GET path='/health' status_code=200 duration_ms=1.234
```

Dependency `get_db` открывает сессию, выполняет `commit` при успехе, `rollback`
при исключении и всегда закрывает сессию. Сервисы создаются в
`backend/api/dependencies.py`; `Depends(get_db, scope="function")` завершает
транзакцию до отправки HTTP-ответа. Фабрика сессий создаётся при первом обращении
к БД, поэтому запуск приложения и `GET /health` не требуют подключения к ней.

Роутеры `dataset`, `analysis`, `ranking`, `graph`, `exports` остаются заготовками
без обработчиков и не отображаются в Swagger UI.

### Репозитории и сервисы

Пользователи следуют тем же слоям: `models/user.py`, `schemas/user.py`,
`repositories/user_repository.py`, `services/user_service.py`. `UserCreate`
принимает email и пароль, `UserService.create` проверяет уникальность email,
хеширует пароль и передаёт репозиторию только email и хеш. `UserRepository`
наследует общий `BaseRepository`. `AuthService` использует `UserService` для
регистрации и поиска аккаунта при входе. Транзакцией, как и для остальных
сущностей, управляет `get_db`; `created_at` задаётся в БД.

Для `Node`, `Edge`, `Transaction`, `Cluster`, `NodeAssessment`, `RankedNode`
доступны классы `<Entity>Repository` и `<Entity>Service` в файлах
`backend/repositories/<entity>_repository.py` и `backend/services/<entity>_service.py`.
Общие методы наследуются из `BaseRepository` и `BaseService`:

- `get_by_id(entity_id)` — поиск по техническому `id`.
- `get_all(skip=0, limit=100)` — страница с устойчивым порядком по `id`;
  `skip` и `limit` — целые неотрицательные числа, `limit=0` возвращает пустой список.
- `create(data)`, `update(entity_id, data)`, `delete(entity_id)` — запись и удаление.

Репозитории принимают словари полей и возвращают ORM-объекты; при отсутствии
записи `get_by_id` и `update` возвращают `None`, `delete` — `False` (при успехе `True`).
Сервисы принимают существующие Pydantic-схемы `Create`/`Update`, возвращают
ORM-объекты, а успешный `delete` возвращает `None`. Для преобразования результата
в схему ответа доступен `NodeResponse.model_validate(node)` и аналоги.

Сервисы проверяют уникальность бизнес-ключей, наличие связанных записей и
условие `n_seed <= n_nodes`. Транзакции требуют существующего направленного
ребра; одинаковые переводы с разными `row_id` сохраняются. Частичные обновления
меняют только переданные поля и проверяют итоговую запись. Явный `None` разрешён
только для nullable-поля `pass_through`.

Ошибки экспортируются из `backend.services`: `NotFoundError`, `ConflictError`,
`ValidationError` (общий предок — `ServiceError`). Эти классы не зависят от HTTP.
Удаление или изменение бизнес-ключа используемой записи блокируется ограничениями
БД и превращается в `ConflictError`; каскадного удаления и пересчёта анализа нет.

Оба слоя используют переданную синхронную `Session`. Записи вызывают `flush`,
а `commit`/`rollback` принадлежат вызывающему коду. После ошибки ограничения БД
нужен rollback; контекст `session.begin()` выполнит его автоматически, если
исключение выйдет из блока:

```python
from sqlalchemy.orm import Session

from backend.core.database import create_db_engine
from backend.repositories import NodeRepository
from backend.schemas import NodeCreate
from backend.services import NodeService

engine = create_db_engine()
with Session(engine) as session, session.begin():
    service = NodeService(NodeRepository(session))
    node = service.create(NodeCreate(gid="example-node", depth=0, is_seed=True))
    node_id = node.id
```

Проверка API, репозиториев, сервисов и миграций на временной SQLite
(HTTP-тесты используют `TestClient`; зависимости включают `httpx` и `httpx2`
для совместимости с поддерживаемыми версиями Starlette):

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\.venv\Scripts\python.exe -W error -m unittest discover -s backend/tests -v
```

## Как запустить локально

Ниже команды для PowerShell. Нужен установленный Python с поддержкой перечисленных библиотек. URL репозитория пока не указан.

### 1. Клонировать репозиторий

Замените `<URL_РЕПОЗИТОРИЯ>` фактическим адресом перед выполнением:

```powershell
git clone <URL_РЕПОЗИТОРИЯ> moneygraph-ai
cd moneygraph-ai
```

Если проект уже скачан, откройте терминал в его корне.

### 2. Установить зависимости

Для backend нужен Python 3.10 или новее. Из корня проекта создайте окружение
и установите зависимости сервера:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Библиотеки анализа и интерфейса не нужны для запуска API. Для тестов установите
`backend/requirements-dev.txt` вместо `backend/requirements.txt`.

### 3. Подготовить .env и данные

```powershell
Copy-Item .env.example .env
```

Не перезаписывайте `.env`, если он уже настроен. Backend читает корневой `.env`
независимо от рабочей папки; сам `.env.example` служит шаблоном. Настройки:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `APP_NAME` | `MoneyGraph AI` | Название приложения в документации API |
| `CORS_ORIGINS` | `["http://localhost:8501","http://127.0.0.1:8501"]` | Разрешённые origins, JSON-массив строк |
| `DATABASE_URL` | `postgresql+psycopg://postgres@localhost:5432/moneygraph` | Подключение к PostgreSQL; настройте в `.env` перед миграцией |
| `JWT_SECRET_KEY` | Нет | Случайный секрет минимум 32 байта в UTF-8 для подписи HS256; обязателен для аутентификации |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Срок действия access-токена, положительное целое число минут |

Пустые значения используют defaults там, где они есть; переменные окружения имеют приоритет над `.env`.
Сервер запускается и без `.env`. CORS допускает методы `GET`, `POST`, `PATCH`, `DELETE` и заголовок
`Content-Type` и `Authorization` для указанных origins; передача credentials выключена.
Для миграции укажите в `.env` существующую базу и пользователя с правом создания таблиц:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DB_NAME
```

Замените заглушки настоящими значениями. Спецсимволы в логине и пароле
кодируются для URL, например `@` → `%40`, `%` → `%25`. Адрес с префиксом
`postgresql://` также поддерживается и использует установленный драйвер psycopg 3.
Alembic создаёт таблицы внутри существующей базы, а не саму базу PostgreSQL.

Перед запуском сервера задайте случайный JWT-секрет. Следующая команда генерирует
его через `secrets.token_urlsafe(32)` и сохраняет в окружении текущего PowerShell:

```powershell
$env:JWT_SECRET_KEY = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$env:ACCESS_TOKEN_EXPIRE_MINUTES = "30"
```

Запускайте Uvicorn в том же окне. Для постоянной настройки сохраните сгенерированный
секрет в `JWT_SECRET_KEY` корневого `.env` и используйте одинаковый ключ во всех
процессах сервера. Не добавляйте `.env` в Git. Замена ключа делает ранее выданные
токены недействительными; готового общего секрета в проекте нет.

### 4. Применить миграции

Из корня проекта:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

При активированной `.venv` эквивалентная команда — `alembic upgrade head`.
Текущая ревизия: `a61f27b90c3d` (таблица `users`), после `28fe255db73e`
(шесть таблиц данных). Повторный запуск `upgrade head` безопасен.
Для запуска из другой папки передайте `-c <абсолютный путь к alembic.ini>`.
Подключение берётся из окружения или корневого `.env`, пароль в `alembic.ini` не хранится.

Создаются таблицы `nodes`, `edges`, `transactions`, `clusters`, `node_assessments`,
`ranked_nodes`, `users` и служебная `alembic_version`. Начальные данные не загружаются.

У каждой сущности есть технический `id`, `created_at`, `updated_at`.
Бизнес-ключи `gid`, `row_id`, `cluster_id` сохраняются отдельно. Временные поля
в PostgreSQL имеют тип `TIMESTAMP WITH TIME ZONE`; `updated_at` обновляется
SQLAlchemy при изменении строки через ORM/Core. Прямой SQL должен обновлять это поле явно.

Денежные суммы — `NUMERIC(20, 2)`, `top_gids` — массив строк PostgreSQL.
Ограничения БД проверяют диапазоны глубины и баллов, роли, длину `evidence`,
уникальность оценки узла, пары рёбер, номера строки транзакции и позиции рейтинга.
`pass_through` допускает `NULL` и значения больше 1 по смыслу исходного плана.

Транзакция ссылается на узлы и на агрегированное ребро по составному ключу
`src/dst`. Сначала сохраняются узлы и рёбра, затем транзакции. Связи
`Transaction.edge` и `Edge.transactions` доступны для чтения; отправитель и
получатель задаются через `src/dst` или `sender/recipient`. Одинаковые переводы
с разными `row_id` разрешены. Удаление используемых узлов, рёбер и кластеров блокируется FK.

В исходном плане `RankedNode` был производной сущностью. По текущему требованию
моделей для всех сущностей он хранится как снимок актуального рейтинга;
его пересчёт вместе с оценками будет задачей будущего сервиса анализа.

Проверки миграции на временной SQLite (PostgreSQL-массив заменяется JSON только в SQLite):

```powershell
.\.venv\Scripts\python.exe -W error -m unittest backend.tests.test_migrations -v
```

Для тех же проверок на PostgreSQL задайте `TEST_DATABASE_URL` в окружении.
Тесты создают отдельную временную схему и удаляют только её; пользователю нужны
права на создание схем. Проверяются upgrade/downgrade, соответствие metadata,
связи, ограничения, временные поля и сохранение повторных переводов.

### 5. Запустить backend

Из корня проекта:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --no-access-log
```

`--no-access-log` отключает второй журнал HTTP-запросов Uvicorn: запросы уже
логирует middleware приложения. Служебные сообщения Uvicorn остаются доступны.

- Проверка: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) → `{"status":"ok"}`.
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- Остановка сервера: `Ctrl+C`.

Датасет для запуска backend не требуется. Для CRUD API нужна доступная база
с применёнными миграциями и access-токен; `GET /health` и Swagger UI работают без подключения к БД.

В другом окне PowerShell зарегистрируйтесь, войдите и выполните защищённый запрос:

```powershell
$apiUrl = "http://127.0.0.1:8000"
$email = Read-Host "Email"
$password = [System.Net.NetworkCredential]::new("", (Read-Host "Пароль" -AsSecureString)).Password
$credentials = @{ email = $email; password = $password } | ConvertTo-Json

$registration = Invoke-RestMethod -Method Post -Uri "$apiUrl/auth/register" -ContentType "application/json; charset=utf-8" -Body $credentials
# Токен регистрации уже подходит для защищённых запросов.
$headers = @{ Authorization = "Bearer $($registration.access_token)" }
Invoke-RestMethod -Uri "$apiUrl/auth/me" -Headers $headers
# При последующих входах получите новый токен через /auth/login.
$auth = Invoke-RestMethod -Method Post -Uri "$apiUrl/auth/login" -ContentType "application/json; charset=utf-8" -Body $credentials
$headers = @{ Authorization = "Bearer $($auth.access_token)" }
Invoke-RestMethod -Uri "$apiUrl/auth/me" -Headers $headers
Invoke-RestMethod -Uri "$apiUrl/nodes/?skip=0&limit=10" -Headers $headers
Remove-Variable password, credentials
```

Если пользователь уже существует, пропустите запрос регистрации. В Swagger UI
вызовите `/auth/register` или `/auth/login` с JSON, скопируйте `access_token`, нажмите **Authorize**
и вставьте только токен: префикс `Bearer` Swagger добавляет сам.

Проверка доступа к данным:

```bash
curl -i http://127.0.0.1:8000/nodes/
# HTTP 401 без токена
curl -i http://127.0.0.1:8000/nodes/ -H "Authorization: Bearer <access_token>"
# HTTP 200 с действующим токеном из ответа регистрации или входа
```

### 6. Запустить существующий аудит данных (отдельно от backend)

Для аудита дополнительно установите библиотеки:

```powershell
.\.venv\Scripts\python.exe -m pip install pandas numpy networkx pyarrow
```

Скрипт анализа не загружает `.env`.

Поместите предоставленный `data (1).zip` в родительскую папку проекта. Это фиксированный путь, используемый текущим скриптом; переименовывать или распаковывать архив не нужно.

```text
<родительская папка>/
├── data (1).zip
└── moneygraph-ai/
    └── analysis/profile_data.py
```

Внутри архива должны находиться `data/nodes.parquet`, `data/edges.parquet` и `data/transactions.parquet`. Для транзакций используются поля `src`, `dst`, `date`, `sum_kzt`; ID операции и времени суток в данных нет.

```powershell
.\.venv\Scripts\python.exe analysis/profile_data.py
```

Скрипт выводит сводку и перезаписывает `analysis/profile.json` и `analysis/node_features.csv`. Исходный архив остаётся неизменным. Для предоставленных данных ожидаются 2 248 строк признаков, `amount_mismatch = 0`, `count_mismatch = 0` и `unknown_endpoints = 0`.

Это запуск аудита, а не готового приложения. Команда полного анализа и запуска интерфейса будет добавлена после их реализации и проверки. При `FileNotFoundError` проверьте расположение архива; при ошибке импорта — установку зависимостей в `.venv`.

## Требования хакатона и границы MVP

Источник требований — предоставленные README датасета, README и код стартера. Отдельного полного ТЗ и валидатора в доступных материалах нет.

Обязательные результаты:

| Файл | Требование |
|---|---|
| `nodes_roles.csv` | Ровно 2 248 строк, включая 19 изолятов; заполненные поля, одна роль на узел, числовое `evidence` до 200 символов |
| `clusters.csv` | Строка на кластер с характеристиками и гипотезой о назначении |
| `top_nodes.csv` | Не менее 20 узлов, отсортированных по убыванию приоритета, с объяснением |

Сохраняются колонки стартера; дополнительные разрешены:

```text
nodes_roles.csv:
gid,role,role_score,cluster_id,priority_score,evidence,in_deg,out_deg,in_kzt,out_kzt,pagerank,pass_through,depth,is_seed,truncated_by_depth

clusters.csv:
cluster_id,n_nodes,n_seed,sum_kzt_internal,top_gids,hypothesis

top_nodes.csv:
rank,gid,role,priority_score,why
```

Допустимые роли: `consolidator`, `transit`, `distributor`, `terminal`, `coordinator`, `peripheral`. `role_score` и `priority_score` находятся в `[0, 1]` и отражают разные показатели: поддержку роли и приоритет проверки.

При реализации обязательно учитывать:

- У 444 узлов четвёртого колена нет наблюдаемых выходов: это граница выгрузки, а не доказательство конечного получения средств. Сохраняется флаг `truncated_by_depth`.
- Входящие потоки неполны, особенно у seed. `pass_through` — отношение наблюдаемых сумм, а не доказанная доля переданных дальше денег.
- Суммы и количество операций — разные признаки. Направление и веса графа сохраняются; неориентированную проекцию для кластеризации нужно явно описать.
- Период ограничен июлем 2026 года, порог перевода — 5 000 KZT. Даты не позволяют устанавливать порядок операций внутри дня.
- 97 повторных строк транзакций нельзя автоматически удалять без ID операции. В браузере идентификаторы нужно передавать строками, чтобы избежать потери точности.
- При нулевом входе `pass_through` неопределён. Стартер оставляет `NaN`, хотя его README требует заполненные колонки; допустимое представление нужно сверить с валидатором организаторов, не выдавая техническую замену за измеренное значение.

При бюджете три часа приоритет — объяснимые правила ролей, кластеры, отдельный рейтинг, три CSV и проверка их схем, чисел и повторяемости. Затем — простой экран и демонстрация одного узла с объяснением за минуту. Временные признаки дают дополнительную ценность по README стартера и добавляются после обязательных результатов. AI-чат, генератор синтетики, обучение без разметки и масштабирование на миллионы узлов в этот план не входят.

## Команда

- **Название команды:** [заполнить]
- **Участники и роли:** [имя — роль; заполнить]
- **Контакт:** [заполнить]
