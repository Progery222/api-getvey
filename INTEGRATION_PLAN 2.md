# План интеграции — Единая система публикации контента
> Дата: 2026-03-30 | Статус: финальный черновик

---

## Принятые решения

| Вопрос | Решение |
|--------|---------|
| Хранение видео | MinIO (self-hosted S3) — локально, веб-UI для скачивания |
| Аккаунтов на телефон | Сейчас 1:1, архитектура готова к N:1 в будущем |
| Источники контента | Любой сервис → orchestrator → телефон (открытая шина) |
| Клиенты | Приносят свои телефоны ИЛИ арендуют наши |
| Одобрение публикации | Нет — полностью автоматически |
| Расписание | Умный AI-планировщик на каждый телефон (anti-ban) |
| Физика | USB-хабы → 1 сервер на старте, несколько серверов позже |

---

## Целевая архитектура

```
┌──────────────────────────────────────────────────────────────────────┐
│                    ATOME STUDIO DASHBOARD                             │
│  React + Three.js | NestJS API                                       │
│  - запуск генерации    - управление фермой    - мониторинг           │
│  - управление клиентами - просмотр/скачивание видео                  │
└───────┬──────────────────┬──────────────────────┬────────────────────┘
        │ REST+WS          │ REST+WS              │ REST+WS
        ▼                  ▼                      ▼
┌───────────────┐  ┌───────────────┐  ┌──────────────────────────────┐
│  SportZavod   │  │ content-zavod │  │  ORCHESTRATOR                │
│  :8000        │  │ :8002         │  │  :8001 (FastAPI + Redis)     │
│               │  │               │  │                              │
│ Спортивный    │  │ Универсальный │  │ Принимает задачи от любого  │
│ контент       │  │ контент       │  │ генератора                  │
│ HeyGen+OpenAI │  │ Replicate+LLM │  │ Умный планировщик           │
└───────┬───────┘  └───────┬───────┘  │ Очередь на публикацию       │
        │                  │          └──────────────┬───────────────┘
        │ POST /api/content/queue                    │ Redis задачи
        └──────────────────┘                        ▼
                 │                     ┌────────────────────────────┐
                 ▼                     │  Workers (phone_001..N)    │
          ┌──────────────┐             │  Python ReAct агенты       │
          │    MinIO     │◄────────────│  ADB → USB → телефоны      │
          │  :9000/:9001 │  скачивает  │  TikTok через экран         │
          │  Web UI      │             └────────────────────────────┘
          └──────────────┘
                                         USB-хаб (32-64 порта)
                                         └── phone_001 ... phone_064
                                         USB-хаб #2 (при расширении)
                                         └── phone_065 ... phone_128
```

---

## Ключевая идея: Orchestrator как универсальная шина

Любой сервис генерации отправляет контент через один и тот же интерфейс:

```
POST http://orchestrator:8001/api/content/queue

{
  "account_id": "uuid",          ← единый ID аккаунта в системе
  "file_url": "http://minio:9000/content/...",
  "content_type": "video",
  "caption": "...",
  "hashtags": ["nba", "highlights"],
  "platform": "tiktok",
  "source_service": "sportzavod"  ← кто создал контент (для аналитики)
}
```

Orchestrator:
1. Находит телефон по `account_id` из PostgreSQL
2. Передаёт Smart Scheduler — тот решает **когда** публиковать
3. Пушит задачу в Redis под конкретный телефон
4. Worker скачивает видео с MinIO и публикует

**Важно:** завтра появится третий генератор — он просто начинает слать на тот же `/api/content/queue`. Никаких изменений в orchestrator.

---

## Smart Scheduler — умный планировщик публикаций

Это новый компонент внутри orchestrator. Для каждого телефона/аккаунта он принимает решение **когда и в каком порядке** выполнять публикации.

### Что учитывает

```python
class SmartScheduler:
    """
    Принимает решение о времени публикации для конкретного аккаунта.

    Факторы решения:
    1. Anti-ban: не публиковать чаще чем раз в N часов
    2. Account health: если много ошибок → снизить активность
    3. Warmup phase: новый аккаунт публикует реже
    4. Peak hours: учитывать timezone аккаунта (аудитория активна вечером)
    5. Queue depth: если накопилась очередь → распределить равномерно
    6. Platform signals: если последний пост получил мало просмотров → пауза
    """

    async def get_next_publish_time(self, account_id: str) -> datetime:
        account = await self.db.get_account(account_id)

        # Базовый интервал из конфига аккаунта (e.g. 8 часов)
        base_interval = account.post_frequency_hours

        # Корректировка под warmup
        if account.warmup_day < 7:
            base_interval *= 2  # молодой аккаунт публикует вдвое реже

        # Корректировка под health score
        if account.health_score < 0.5:
            base_interval *= 3  # признаки бана → сильно снизить активность

        # Найти следующий peak hour в timezone аккаунта
        next_peak = self.find_next_peak_hour(
            timezone=account.timezone,
            preferred_hours=[9, 12, 17, 20, 22],  # типичные пики TikTok
            not_before=last_post_time + timedelta(hours=base_interval)
        )

        return next_peak
```

### Account health score (0.0 → 1.0)
```
1.0 = всё отлично
0.7 = повышенный риск (снизить активность)
0.3 = высокий риск (только просмотры, никаких постов)
0.0 = бан или ограничение (остановить всё)

Формируется из:
- % успешных публикаций за последние 7 дней
- Количество ошибок при загрузке видео
- Время с последнего успешного поста
- Факт бана/ограничения (детектируется worker'ом)
```

---

## Мультитенантность

### Две модели клиентов

**Модель 1: BYOD (Bring Your Own Devices)**
Клиент подключает свои телефоны к системе.
Его телефоны помечены его `tenant_id`.
Он видит только своих телефонов и аккаунтов.

**Модель 2: Аренда**
Клиент не имеет телефонов — использует наши.
Назначаем ему телефоны из пула, помечаем `tenant_id`.
Аккаунты в TikTok создаём/прогреваем под его нишу.

### Схема данных

```sql
-- Тенанты
CREATE TABLE tenants (
    tenant_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(100) NOT NULL,
    plan         VARCHAR(20)  DEFAULT 'basic',   -- basic | pro | enterprise
    max_phones   INTEGER      DEFAULT 10,
    max_posts_day INTEGER     DEFAULT 100,
    is_active    BOOLEAN      DEFAULT TRUE,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- Пользователи (логины в Dashboard)
CREATE TABLE users (
    user_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID REFERENCES tenants(tenant_id),
    email        VARCHAR(200) UNIQUE NOT NULL,
    role         VARCHAR(20)  DEFAULT 'tenant_admin', -- super_admin | tenant_admin | viewer
    password_hash TEXT NOT NULL,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- Телефоны — добавить tenant_id
ALTER TABLE phones ADD COLUMN tenant_id UUID REFERENCES tenants(tenant_id);

-- Единая таблица аккаунтов (замена Google Sheets + devices.json)
CREATE TABLE accounts (
    account_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID REFERENCES tenants(tenant_id) NOT NULL,
    phone_id         VARCHAR(20) REFERENCES phones(phone_id),
    platform         VARCHAR(20) DEFAULT 'tiktok',
    username         VARCHAR(100),
    niche            VARCHAR(100),        -- sports_nba | lifestyle | fitness...
    content_sources  TEXT[],              -- ['sportzavod', 'contentzavod']
    heygen_avatar_id VARCHAR(100),        -- если SportZavod
    post_frequency_hours INTEGER DEFAULT 8,
    timezone         VARCHAR(50) DEFAULT 'America/New_York',
    health_score     FLOAT DEFAULT 1.0,
    warmup_day       INTEGER DEFAULT 0,
    status           VARCHAR(20) DEFAULT 'warmup',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- tasks, actions_log — добавить tenant_id
ALTER TABLE tasks ADD COLUMN tenant_id UUID REFERENCES tenants(tenant_id);
ALTER TABLE actions_log ADD COLUMN tenant_id UUID REFERENCES tenants(tenant_id);
```

### Изоляция данных

В orchestrator каждый запрос проверяет `tenant_id` из JWT токена:
```python
# Все запросы к БД фильтруются по tenant_id
accounts = await db.execute(
    "SELECT * FROM accounts WHERE tenant_id = $1",
    current_user.tenant_id  # из JWT
)

# MinIO: папки изолированы per tenant
file_path = f"{tenant_id}/{account_id}/video.mp4"
```

---

## Структура MinIO (хранилище видео)

```
minio bucket: "content"
├── {tenant_id}/
│   ├── sportzavod/
│   │   ├── {account_id}/
│   │   │   └── 2026-03/
│   │   │       ├── abc123_final.mp4      ← готовое видео
│   │   │       └── abc123_thumbnail.jpg  ← превью
│   └── contentzavod/
│       └── {account_id}/
│           └── 2026-03/
│               └── edited_20260330.mp4
```

**Веб-интерфейс MinIO Console (`:9001`):**
- Заходишь в браузере → видишь все файлы по папкам
- Фильтр по тенанту, аккаунту, дате
- Прямое скачивание любого видео
- Можно настроить retention policy (автоудаление старых файлов)

---

## Изменения по каждому сервису

### SportZavod (:8000)

**Добавить:**
```
agent/
├── minio_uploader.py     ← загрузка MP4 в MinIO после генерации
└── content_bridge.py     ← POST /api/content/queue в orchestrator
```

**Изменить:**
- `agent/pipeline.py`: после генерации → upload MinIO → call orchestrator
- `agent/account_manager.py`: добавить `account_id` (UUID) в модель Account
- Убрать загрузку в Google Drive (оставить как backup опционально)

**Формат вызова orchestrator:**
```python
await content_bridge.queue(
    account_id=account.account_id,
    file_url=minio_url,
    caption=script.description,
    hashtags=script.tags,
    source_service="sportzavod"
)
```

---

### content-zavod (:8002)

**Добавить:**
```
bot/
├── api/
│   ├── main.py           ← uvicorn сервер :8002
│   ├── routes.py         ← POST /api/generate, GET /api/jobs/{id}
│   └── content_bridge.py ← POST /api/content/queue в orchestrator
```

**Изменить:**
- `services/publisher.py`: убрать прямой TikTok/YouTube → вызов orchestrator
- После одобрения в Telegram (кнопка "Да") → upload MinIO → orchestrator
- Если запуск из Dashboard → `/api/generate` → пайплайн → upload → orchestrator

---

### admin-panel / orchestrator (:8001)

**Добавить:**
```
src/
├── api/
│   ├── content.py        ← уже есть, расширить
│   ├── accounts.py       ← CRUD аккаунтов (новый)
│   ├── tenants.py        ← управление тенантами (новый)
│   └── metrics.py        ← агрегированные метрики для Dashboard (новый)
├── services/
│   ├── smart_scheduler.py ← умный планировщик (новый, ключевой!)
│   ├── health_monitor.py  ← мониторинг здоровья аккаунтов (новый)
│   └── minio_client.py    ← клиент MinIO (новый)
└── websocket/
    └── events.py          ← WS /ws/events → real-time в Dashboard (новый)
```

**Изменить:**
- `content.py`: принимать `account_id` вместо `phone_id`/`role`
- `content.py`: убрать TODO, добавить smart_scheduler.get_next_publish_time()
- `devices.py`: читать из PostgreSQL вместо devices.json

**Новые эндпоинты:**
```
POST /api/accounts          ← создать аккаунт
GET  /api/accounts          ← список аккаунтов (фильтр по tenant)
GET  /api/metrics           ← метрики для Dashboard
GET  /api/metrics/{phone_id} ← метрики конкретного телефона
WS   /ws/events             ← real-time события
```

---

### atome-studio-ui (Dashboard)

**Добавить в apps/api:**
```
src/
├── adapters/
│   ├── sportzavod.adapter.ts   ← GET /api/jobs, /api/accounts от SportZavod
│   ├── farm.adapter.ts         ← GET /api/status, WS /ws/events от orchestrator
│   └── contentzavod.adapter.ts ← GET /api/jobs от content-zavod
├── minio/
│   └── minio.service.ts        ← список файлов для скачивания
└── auth/
    └── (уже есть) jwt + tenant check
```

**Добавить в apps/web:**
```
src/
├── pages/
│   ├── Accounts.tsx      ← список аккаунтов + привязка к телефону
│   ├── Generate.tsx      ← запуск генерации (SportZavod / content-zavod)
│   ├── Queue.tsx         ← очередь публикаций, real-time статусы
│   ├── Phones.tsx        ← ферма телефонов (перенести из 04-dashboard)
│   ├── Videos.tsx        ← библиотека видео в MinIO + скачивание
│   └── Clients.tsx       ← управление тенантами (только super_admin)
└── stores/
    ├── accounts.ts       ← Zustand store
    ├── queue.ts          ← Zustand store
    └── phones.ts         ← Zustand store
```

**services.json для 3D галактики:**
```json
[
  {
    "id": "sportzavod",
    "name": "Sport Zavod",
    "color": "#00ffcc",
    "api_url": "http://localhost:8000",
    "processes": [
      { "id": "news", "label": "Поиск новостей" },
      { "id": "script", "label": "Генерация сценария" },
      { "id": "video", "label": "Создание видео" },
      { "id": "upload", "label": "Загрузка в очередь" }
    ]
  },
  {
    "id": "orchestrator",
    "name": "Orchestrator",
    "color": "#ff6b00",
    "api_url": "http://localhost:8001",
    "processes": [
      { "id": "scheduler", "label": "Smart Scheduler" },
      { "id": "queue", "label": "Redis Queue" },
      { "id": "workers", "label": "Phone Workers" }
    ]
  },
  {
    "id": "contentzavod",
    "name": "Content Zavod",
    "color": "#7b2dff",
    "api_url": "http://localhost:8002",
    "processes": [
      { "id": "search", "label": "Поиск новостей" },
      { "id": "generate", "label": "Генерация видео" },
      { "id": "edit", "label": "Монтаж" }
    ]
  }
]
```

---

## Полный поток данных

```
1. ЗАПУСК ГЕНЕРАЦИИ
   Dashboard → POST http://sportzavod:8000/api/generate
   { account_ids: ["uuid1", "uuid2"], videos_per_account: 1 }

2. ГЕНЕРАЦИЯ (SportZavod)
   Brave Search → LLM сценарий → HeyGen видео → FFmpeg монтаж
   Готовый MP4: 1080x1920, ~30-60 секунд

3. ЗАГРУЗКА В MINIO
   SportZavod → PUT http://minio:9000/content/{tenant}/{account}/video.mp4
   Возвращает: http://minio:9000/content/tenant_abc/acc_123/video.mp4

4. ПОСТАНОВКА В ОЧЕРЕДЬ
   SportZavod → POST http://orchestrator:8001/api/content/queue
   {
     account_id: "uuid1",
     file_url: "http://minio:9000/...",
     caption: "NBA Finals highlights 🔥",
     hashtags: ["nba", "basketball"],
     source_service: "sportzavod"
   }

5. SMART SCHEDULER (orchestrator)
   - Смотрит account: timezone=America/New_York, warmup_day=15, health=0.95
   - Последний пост был 6 часов назад, post_frequency=8h
   - Следующий peak hour в EST: сегодня в 20:00 (через 3ч)
   - Ставит delayed task в Redis: scheduled_at=20:00

6. WORKER (phone_007, через 3 часа)
   - Читает задачу из Redis
   - Скачивает MP4 с MinIO URL
   - Делает warmup: смотрит 20 видео по niche=sports_nba
   - Загружает видео в TikTok через ADB + GPT-4o Vision
   - Пишет caption + hashtags
   - Нажимает "Опубликовать"
   - Логирует: actions_log {success: true, action: post_video}

7. СОБЫТИЯ В REAL-TIME
   Worker → Redis pub/sub → Orchestrator WS → Dashboard
   { event: "published", account: "@nba_acc_01", platform: "tiktok" }

8. МОНИТОРИНГ
   Dashboard обновляет:
   - Счётчик публикаций сегодня
   - health_score аккаунта
   - Статус в 3D галактике (атом пульсирует зелёным)
```

---

## Docker Compose (полная система)

```yaml
# docker-compose.yml (в корне oure/)
version: "3.9"

services:

  minio:
    image: minio/minio
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Web Console (для скачивания)
    volumes:
      - ./minio_data:/data
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: changeme123
    command: server /data --console-address ":9001"

  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: farm
      POSTGRES_USER: farm
      POSTGRES_PASSWORD: farm123
    volumes:
      - ./postgres_data:/var/lib/postgresql/data
      - ./admin-panel 2/services/database/migrations:/docker-entrypoint-initdb.d

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  orchestrator:
    build: "./admin-panel 2/services/05-orchestrator"
    ports:
      - "8001:8001"
    depends_on: [postgres, redis, minio]
    env_file: "./admin-panel 2/services/05-orchestrator/.env"

  sportzavod:
    build: "./SportZavod 2"
    ports:
      - "8000:8000"
    depends_on: [orchestrator, minio]
    env_file: "./SportZavod 2/.env"

  contentzavod:
    build: "./content-zavod 2"
    ports:
      - "8002:8002"
    depends_on: [orchestrator, minio, redis, postgres]
    env_file: "./content-zavod 2/.env"

  dashboard-api:
    build: "./atome-studio-ui 2/apps/api"
    ports:
      - "3001:3001"
    depends_on: [orchestrator, sportzavod, contentzavod]

  dashboard-web:
    build: "./atome-studio-ui 2/apps/web"
    ports:
      - "5173:80"
    depends_on: [dashboard-api]
```

---

## Фазы реализации

### Фаза 1 — Хранилище + базовая связка (3-5 дней)
```
[ ] Поднять MinIO через docker-compose
[ ] SportZavod: minio_uploader.py — загрузка MP4 после генерации
[ ] SportZavod: content_bridge.py — вызов POST /api/content/queue
[ ] Orchestrator: принимать account_id (не phone_id/role)
[ ] Таблица accounts в PostgreSQL — импорт 28 аккаунтов из Google Sheets
[ ] Тест: сгенерировать видео → оно в MinIO → задача в Redis → worker скачивает
```

### Фаза 2 — Smart Scheduler + health monitoring (3-5 дней)
```
[ ] SmartScheduler: расчёт времени публикации по timezone + warmup + health
[ ] HealthMonitor: обновление health_score после каждого действия worker'а
[ ] Orchestrator WebSocket /ws/events → real-time события
[ ] Тест: задача ставится на delayed time, worker выполняет в нужное время
```

### Фаза 3 — Dashboard управляет всем (1-2 недели)
```
[ ] Адаптеры в atome-studio-ui/api (sportzavod, farm, contentzavod, minio)
[ ] Страница Accounts — CRUD, привязка к телефону
[ ] Страница Generate — запуск SportZavod / content-zavod из UI
[ ] Страница Queue — очередь с real-time статусами через WS
[ ] Страница Phones — мониторинг фермы (из 04-monitoring-dashboard)
[ ] Страница Videos — MinIO браузер с скачиванием
[ ] Закрыть 04-monitoring-dashboard (заменён Dashboard)
```

### Фаза 4 — content-zavod как сервис (3-5 дней)
```
[ ] REST API на :8002 (POST /api/generate, GET /api/jobs/:id)
[ ] После генерации → MinIO → orchestrator (без Telegram одобрения)
[ ] Telegram бот: показывает видео но всё равно публикует автоматически (уведомление)
[ ] Dashboard: запуск content-zavod для любого аккаунта
```

### Фаза 5 — Мультитенантность (1-2 недели)
```
[ ] Таблицы tenants + users + JWT авторизация
[ ] tenant_id во всех таблицах + middleware фильтрация
[ ] Dashboard: логин/регистрация
[ ] Dashboard: страница Clients (super_admin)
[ ] MinIO: bucket policy per tenant
[ ] Модель аренды телефонов: назначение из пула
```

### Фаза 6 — Масштаб 500+ телефонов (ongoing)
```
[ ] Убрать devices.json полностью → только PostgreSQL
[ ] Horizontal scaling workers через Redis (уже заложено)
[ ] Мониторинг производительности через PostHog (MCP уже есть)
[ ] Авто-обнаружение новых USB устройств
[ ] Load balancing для orchestrator (если нужно несколько серверов)
```

---

## Порты локального запуска

| Сервис | Порт | Назначение |
|--------|------|------------|
| MinIO API | 9000 | S3 хранилище видео |
| MinIO Console | 9001 | Веб-UI для просмотра/скачивания |
| PostgreSQL | 5432 | Единая база данных |
| Redis | 6379 | Очередь задач |
| SportZavod | 8000 | Генератор спортивного контента |
| Orchestrator | 8001 | Шина публикаций + Smart Scheduler |
| content-zavod | 8002 | Генератор универсального контента |
| Dashboard API | 3001 | NestJS backend |
| Dashboard Web | 5173 | React frontend |

---

## Что НЕ делаем (anti-scope)

- Google Drive — убираем как основное хранилище (MinIO лучше)
- 04-monitoring-dashboard — заменяем atome-studio-ui полностью
- Прямая публикация в TikTok API из генераторов — только через orchestrator
- Ручное одобрение видео — полный автомат
- Несколько серверов для телефонов — пока всё на USB-хабах к одному серверу

---

## КАК РАБОТАЕТ КАЖДЫЙ СЕРВИС СЕЙЧАС — и что добавить

---

### 1. SportZavod — как работает сейчас

**Запуск:**
Telegram бот ИЛИ `POST /api/generate` → `core/generation_service.py` → создаёт Job в памяти → запускает `run_pipeline()`.

**Пайплайн (7 этапов):**
```
Stage 1: fetch_news()          → Brave Search API, собирает новости за 48ч
Stage 2: score_news()          → LLM оценивает виральность, выбирает TOP-3
Stage 3: analyze_top3()        → LLM глубокий контент-анализ каждой новости
Stage 4: generate_scripts()    → LLM пишет сценарии под стиль аккаунта
Stage 5: generate_video_plans()→ LLM создаёт визуальные планы для видео
Stage 6: generate_meta()       → LLM генерирует заголовки, теги, offer_text
Stage 7: enqueue_video_job()   → ЗАПИСЫВАЕТ В SQLITE, не в Redis
```

**Что происходит после пайплайна:**
- `VideoJob` с `status=pending` записывается в `storage/sportzavod.db`
- Отдельный `agent/queue_worker.py` (воркер) в бесконечном цикле читает `load_pending_jobs()` из SQLite
- Воркер вызывает HeyGen API → polling статуса → скачивает mp4 → сохраняет в `storage/videos/{job_id}_final.mp4`
- Затем звонит `agent/editor.py` → FFmpeg монтаж → `{job_id}_final.mp4`
- После: загружает в Google Drive, обновляет статус в SQLite
- **Публикации в TikTok нет вообще.** Есть `bot/publisher.py` но он не вызывается из пайплайна.

**Хранилище:**
```
storage/
├── sportzavod.db      ← SQLite: runs + video_jobs (ТОЛЬКО у SportZavod, изолировано)
├── videos/            ← готовые MP4 (локальные файлы, теряются при перезапуске)
└── runs/              ← JSON дамп каждого запуска
```

**Аккаунты:** Google Sheets → `agent/sheets_manager.py` → `agent/account_manager.py` → хранит в памяти. При рестарте — перечитывает из Sheets.

**Что НЕ работает / чего нет:**
- Нет связи с orchestrator — видео лежат в `storage/videos/` и никуда не уходят
- Google Drive не работает как источник URL (нельзя передать в orchestrator)
- `account_id` в модели это просто int (порядковый номер), не UUID — несовместимо с farm
- Нет REST endpoint для получения статуса конкретного job в реальном времени

---

**Что добавить в SportZavod:**

```
agent/
├── minio_uploader.py     НОВЫЙ
│   # После того как воркер сохранил {job_id}_final.mp4 в storage/videos/
│   # → загружает в MinIO: content/{tenant_id}/{account_id}/{date}/{job_id}.mp4
│   # → возвращает публичный URL: http://minio:9000/content/...
│
└── content_bridge.py     НОВЫЙ
    # POST http://orchestrator:8001/api/content/queue
    # {
    #   account_id: account.account_uuid,  ← добавить UUID в модель Account
    #   file_url: minio_url,
    #   caption: meta.description,
    #   hashtags: meta.tags,
    #   source_service: "sportzavod"
    # }
```

**Изменить в существующем коде:**

| Файл | Изменение |
|------|-----------|
| `agent/models.py` → `VideoJob` | Добавить `minio_url: str \| None = None` |
| `agent/account_manager.py` → `Account` | Добавить `account_uuid: str` (UUID для связи с farm БД) |
| `agent/queue_worker.py` → после скачивания видео | Вызвать `minio_uploader.upload()` → `content_bridge.queue()` |
| `agent/storage.py` → `video_jobs` таблица | Добавить столбец `minio_url TEXT` |

**Что НЕ трогать:** весь пайплайн (stages 1-7), HeyGen интеграция, FFmpeg монтаж, Google Sheets — они работают.

---

### 2. content-zavod — как работает сейчас

**Запуск:**
Только через Telegram бот. Пользователь пишет тему → FSM State Machine запускает `run_pipeline()`.

**Пайплайн (6 шагов):**
```
Step 1: search_news(topic)          → Brave Search, находит статьи
Step 2: llm.analyze_relevance()     → LLM score 0-1, если < 0.5 → отказ
Step 3: llm.generate_script()       → title, description, video_prompt, tags
Step 4: generate_video(video_prompt)→ Replicate/Kie.ai API → скачивает MP4
Step 5: overlay_title(mp4, title)   → FFmpeg накладывает заголовок
Step 6: bot.send_video() + кнопки  → пользователь видит результат
```

**Что происходит после пайплайна:**
- Если пользователь нажал "Да" → `publisher.py` вызывается, но он **заглушка** (raise NotImplementedError или пустой return)
- Если "Нет" → файл удаляется через `file_manager.cleanup_files()`
- Видео хранится в `media/{user_id}/edited_YYYYMMDD_HHMMSS.mp4` — **временная папка**
- В PostgreSQL пишется только аналитика: user_id, query, cost, duration. Не сам контент.

**Нет:**
- REST API (только Telegram)
- Связи с orchestrator
- Постоянного хранилища видео — файлы удаляются

---

**Что добавить в content-zavod:**

```
bot/
├── api/
│   ├── server.py         НОВЫЙ — uvicorn :8002
│   └── routes.py         НОВЫЙ
│       POST /api/generate  → принимает {account_id, topic} → запускает пайплайн в фоне
│       GET  /api/jobs/:id  → статус генерации
│       GET  /health        → для Dashboard
│
└── services/
    ├── minio_uploader.py   НОВЫЙ — то же что в SportZavod
    └── content_bridge.py   НОВЫЙ — то же что в SportZavod
```

**Изменить:**

| Файл | Изменение |
|------|-----------|
| `services/publisher.py` | Заменить заглушку на: upload MinIO → call orchestrator |
| `handlers/approve.py` | После "Да": вместо publisher → content_bridge.queue() |
| `utils/file_manager.py` | НЕ удалять файл сразу — дождаться загрузки в MinIO |

**Что НЕ трогать:** весь пайплайн (шаги 1-5), Telegram бот, FSM, LLM интеграции.

---

### 3. admin-panel / orchestrator — как работает сейчас

**Что запущено:**
FastAPI сервер `:8001`. При старте (`lifespan`):
1. `process_manager.start()` → поднимает sub-процессы worker'ов
2. `load_devices()` → читает `shared/config/devices.json`
3. `run_drainer()` → фоновый таск который читает действия из Redis и пишет в PostgreSQL

**Orchestrator принимает:**
- `POST /api/content/queue` → валидирует, находит телефон, пушит в Redis `content:queue:{phone_id}`
- Сейчас ищет устройство по `phone_id` или `role` — **UUID аккаунта не поддерживается**

**Worker (06-worker) — как работает:**
```python
# Каждый цикл worker'а (agent.py):
1. scenario_runner.check_and_run()
   → RPOP из Redis content:queue:{phone_id}
   → Anti-ban проверки (warmup_day, posts_today, engagement ratio)
   → _execute_publish() ← ЗАГЛУШКА: asyncio.sleep(3); return True
   → Реального ADB upload НЕТ

2. vision_decide()
   → GPT-4o смотрит скриншот экрана (adb_utils.take_screenshot)
   → Решает: watch | like | comment | swipe | follow

3. vision_execute()
   → ADB команда на телефон

4. check_for_ban()
   → Ищет текст бана на экране

5. _publish_heartbeat()
   → Redis: worker:status:{phone_id} = {status, likes_today, ...}
```

**Redis ключи которые уже работают:**
```
content:queue:{phone_id}    ← задачи на публикацию (RPOP/LPUSH)
content:task:{task_id}      ← метаданные задачи (статус, phone_id)
account:context:{phone_id}  ← поведенческий контекст аккаунта
worker:status:{phone_id}    ← heartbeat от воркера (TTL 5 мин)
worker:events               ← pub/sub канал событий (ban, error)
trainer:action_queue        ← очередь действий для trainer'а
```

**Что НЕ работает:**
- `_execute_publish()` — заглушка, реального ADB upload нет
- `devices.py` — читает из `devices.json`, не из PostgreSQL
- Нет `account_id` (UUID) — только `phone_id` и `role`
- Нет WebSocket для Dashboard
- Нет Smart Scheduler — задачи публикуются немедленно (без учёта времени)
- Нет health score аккаунтов
- CORS разрешён только для `localhost:8080` — Dashboard на `:5173` не пустит

---

**Что добавить / изменить в orchestrator:**

```
src/
├── api/
│   ├── content.py       ИЗМЕНИТЬ: принимать account_id → резолвить phone_id из PostgreSQL
│   ├── accounts.py      НОВЫЙ: CRUD /api/accounts
│   └── metrics.py       НОВЫЙ: GET /api/metrics → для Dashboard
│
├── services/
│   ├── smart_scheduler.py  НОВЫЙ: расчёт времени публикации
│   ├── health_monitor.py   НОВЫЙ: обновление health_score из actions_log
│   └── minio_client.py     НОВЫЙ: проверка доступности file_url
│
└── websocket/
    └── events.py        НОВЫЙ: WS /ws/events → real-time для Dashboard
```

**Изменить:**

| Файл | Изменение |
|------|-----------|
| `main.py` | CORS добавить `localhost:5173` и `localhost:3001` |
| `api/devices.py` | Читать из PostgreSQL вместо `devices.json` |
| `api/content.py` | Принимать `account_id` UUID, резолвить phone_id через `SELECT phone_id FROM accounts WHERE account_id=$1` |
| `api/content.py` | Вызывать `smart_scheduler.get_next_publish_time()` перед push в Redis |
| `worker/worker/scenario_runner.py` | `_execute_publish()` — реализовать реальный ADB upload (скачать с MinIO URL, загрузить в TikTok) |

---

### 4. atome-studio-ui (Dashboard) — как работает сейчас

**Что запущено:**
- `apps/web` (React + Three.js): 3D галактика атомов, работает
- `apps/api` (NestJS): поднят, каждые 30 секунд вызывает `mcp.fetchAllServices()`

**Откуда берутся данные сейчас:**

`McpService.fetchAllServices()` вызывает 3 адаптера параллельно:
- `CloudflareAdapter.fetchServices()` → Cloudflare Workers API
- `PosthogAdapter.fetchServices()` → PostHog Dashboards + Insights
- `PostmanAdapter.fetchServices()` → Postman Collections

**Проблема:** эти адаптеры показывают Cloudflare Workers, PostHog инсайты и Postman коллекции — **не твои сервисы**.

**Zustand store (web):**
```typescript
// services.ts
const DEMO_SERVICES = [
  { name: 'tracker-worker', platform: 'Cloudflare', ... },
  { name: 'My App Dashboard', platform: 'PostHog', ... },
  // ... 10 демо объектов
]
// Реальный polling НЕ настроен — Store показывает DEMO_SERVICES
```

Фронтенд вообще не подключён к `apps/api`. Он показывает захардкоженные демо-данные. API работает отдельно.

**Что есть и работает:**
- 3D галактика отрисовывается красиво
- Three.js атомы, орбиты, анимации — всё готово
- `SidePanel` показывает детали сервиса при клике
- `Sparkline` графики — но на случайных данных

**Что НЕ работает:**
- Фронтенд не опрашивает свой же NestJS API
- NestJS не знает о SportZavod, content-zavod, orchestrator
- Нет страниц управления (только просмотр)
- Нет авторизации
- Нет WebSocket подключения к orchestrator

---

**Что добавить в atome-studio-ui:**

**В `apps/api`:**

```typescript
// 1. Новые адаптеры для внутренних сервисов
src/adapters/
├── sportzavod.adapter.ts    НОВЫЙ
│   // GET http://localhost:8000/api/jobs → статус генераций
│   // GET http://localhost:8000/api/accounts → список аккаунтов
│   // Маппинг в Service { id, name, status, processes }
│
├── farm.adapter.ts          НОВЫЙ
│   // GET http://localhost:8001/api/status → статус фермы
│   // GET http://localhost:8001/api/devices → телефоны
│   // WS  ws://localhost:8001/ws/events → real-time события
│
└── contentzavod.adapter.ts  НОВЫЙ
    // GET http://localhost:8002/health → alive?
    // GET http://localhost:8002/api/jobs → активные задачи

// 2. Добавить адаптеры в McpService.fetchAllServices()
// 3. Новые роуты для управления
src/
├── accounts/accounts.controller.ts  НОВЫЙ: проксирует /api/accounts в orchestrator
├── generate/generate.controller.ts  НОВЫЙ: запуск генерации → SportZavod/content-zavod
└── queue/queue.controller.ts        НОВЫЙ: очередь публикаций → orchestrator
```

**В `apps/web`:**

```typescript
// 1. Подключить store к реальному API (убрать DEMO_SERVICES)
stores/services.ts
  // Каждые 30с: fetch('http://localhost:3001/api/services') → setServices()
  // WebSocket на ws://localhost:3001/ws → updateServiceStatus()

// 2. Новые страницы
pages/
├── Accounts.tsx   // список аккаунтов, привязка к телефону
├── Generate.tsx   // выбрать аккаунт + сервис → запустить генерацию
├── Queue.tsx      // очередь публикаций + real-time статусы
├── Phones.tsx     // ферма (данные из orchestrator)
└── Videos.tsx     // MinIO браузер + скачивание
```

**Изменить:**

| Файл | Изменение |
|------|-----------|
| `apps/web/src/stores/services.ts` | Убрать `DEMO_SERVICES`, добавить fetch к `localhost:3001/api/services` |
| `apps/api/src/mcp/mcp.service.ts` | Добавить sportzavod + farm + contentzavod адаптеры в `fetchAllServices()` |

---

## Итоговая карта: что реально работает, что заглушка, что отсутствует

| Компонент | Статус |
|-----------|--------|
| SportZavod: пайплайн генерации | ✅ Работает |
| SportZavod: сохранение в SQLite | ✅ Работает |
| SportZavod: загрузка в Google Drive | ⚠️ Нестабильно |
| SportZavod: загрузка в MinIO | ❌ Нет |
| SportZavod: отправка в orchestrator | ❌ Нет |
| content-zavod: пайплайн генерации | ✅ Работает |
| content-zavod: publisher.py | ❌ Заглушка |
| content-zavod: REST API | ❌ Нет |
| content-zavod: загрузка в MinIO | ❌ Нет |
| Orchestrator: приём задач `/api/content/queue` | ✅ Работает |
| Orchestrator: Redis очередь | ✅ Работает |
| Orchestrator: резолв по phone_id/role | ✅ Работает |
| Orchestrator: резолв по account UUID | ❌ Нет |
| Orchestrator: Smart Scheduler | ❌ Нет |
| Orchestrator: WebSocket events | ❌ Нет |
| Worker: ReAct loop (watch/like/comment) | ✅ Работает |
| Worker: ADB управление телефоном | ✅ Работает |
| Worker: проверка бана | ✅ Работает |
| Worker: heartbeat в Redis | ✅ Работает |
| Worker: реальная публикация видео в TikTok | ❌ Заглушка |
| Worker: скачивание видео с MinIO URL | ❌ Нет |
| Dashboard: 3D галактика визуализация | ✅ Работает (демо-данные) |
| Dashboard: подключение к внутренним сервисам | ❌ Нет |
| Dashboard: управление (запуск генерации) | ❌ Нет |
| Dashboard: авторизация | ❌ Нет (Auth модуль есть, не подключён) |
| MinIO хранилище | ❌ Не развёрнуто |
| PostgreSQL: схема фермы | ✅ Миграции готовы |
| PostgreSQL: таблица accounts (UUID) | ❌ Нет |
| PostgreSQL: мультитенантность | ❌ Нет |
