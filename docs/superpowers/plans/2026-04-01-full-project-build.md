# Единая система генерации и публикации контента — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить полную микросервисную систему: генерация спортивного/универсального контента → очередь → автопубликация на TikTok через USB-телефоны.

**Architecture:** Пять микросервисов (SportZavod, ContentZavod, Orchestrator, Dashboard API, Workers) общаются через внутреннюю Docker-сеть. Единая точка входа — Traefik API Gateway на :8080. Orchestrator принимает задачи на публикацию от любого генератора и через Smart Scheduler распределяет их по Workers (ReAct-агентам), управляющим телефонами через ADB.

**Tech Stack:** Python 3.12 / FastAPI, NestJS 10, React 18, PostgreSQL 16, Redis 7, MinIO, Traefik v3, Docker Compose, HeyGen API, OpenAI API, Replicate API

---

## Карта файлов

```
api-getvey/
├── docker-compose.yml              # главный compose, все сервисы
├── .env.example                    # шаблон переменных окружения
├── traefik/
│   └── traefik.yml                 # конфиг Traefik
├── orchestrator/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint
│   │   ├── database.py             # SQLAlchemy async engine
│   │   ├── models.py               # Phone, Account, Task ORM
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── routes/
│   │   │   ├── content.py          # POST /api/content/queue
│   │   │   └── phones.py           # CRUD телефонов/аккаунтов
│   │   ├── scheduler.py            # SmartScheduler
│   │   └── redis_client.py         # Redis pub/sub + queues
│   └── tests/
│       ├── test_queue.py
│       └── test_scheduler.py
├── sportzavod/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── heygen_client.py        # HeyGen API wrapper
│   │   ├── openai_client.py        # OpenAI script generation
│   │   └── routes/generate.py     # POST /api/generate
│   └── tests/test_generate.py
├── contentzavod/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── replicate_client.py     # Replicate API wrapper
│   │   └── routes/generate.py     # POST /api/generate
│   └── tests/test_generate.py
├── workers/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── worker.py                   # ReAct агент, слушает Redis
│   ├── adb_controller.py           # ADB команды (tap, swipe, upload)
│   ├── tiktok_publisher.py         # TikTok публикация через экран
│   └── tests/test_publisher.py
└── dashboard-api/
    ├── Dockerfile
    ├── package.json
    ├── src/
    │   ├── main.ts
    │   ├── app.module.ts
    │   ├── phones/                 # CRUD телефонов
    │   ├── tasks/                  # просмотр задач
    │   └── auth/                   # JWT
    └── test/app.e2e-spec.ts
```

---

## Фаза 1: Инфраструктура

### Task 1: .env и docker-compose базовая структура

**Files:**
- Create: `.env.example`
- Create: `docker-compose.yml`

- [ ] **Step 1: Создай `.env.example`**

```bash
# PostgreSQL
POSTGRES_USER=admin
POSTGRES_PASSWORD=secret
POSTGRES_DB=getvey

# Redis
REDIS_URL=redis://redis:6379

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_BUCKET=content

# JWT
JWT_SECRET=change-me-in-production

# API Keys (заполни свои)
OPENAI_API_KEY=
HEYGEN_API_KEY=
REPLICATE_API_TOKEN=
```

- [ ] **Step 2: Создай `docker-compose.yml` с базовыми сервисами**

```yaml
version: "3.9"

networks:
  internal:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  minio_data:

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - internal
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    networks:
      - internal
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - minio_data:/data
    networks:
      - internal
    ports:
      - "9001:9001"   # MinIO UI только для разработки
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      retries: 5
```

- [ ] **Step 3: Запусти и проверь**

```bash
cp .env.example .env
docker compose up postgres redis minio -d
docker compose ps
```

Ожидаемый вывод: все три сервиса в статусе `healthy`.

- [ ] **Step 4: Commit**

```bash
git add .env.example docker-compose.yml
git commit -m "feat: infrastructure — postgres, redis, minio"
```

---

### Task 2: Traefik API Gateway

**Files:**
- Create: `traefik/traefik.yml`
- Modify: `docker-compose.yml` — добавить сервис `traefik`

- [ ] **Step 1: Создай `traefik/traefik.yml`**

```yaml
api:
  dashboard: true
  insecure: true   # dashboard на :8081, только для разработки

entryPoints:
  web:
    address: ":80"

providers:
  docker:
    exposedByDefault: false
    network: internal

log:
  level: INFO
```

- [ ] **Step 2: Добавь Traefik в `docker-compose.yml`**

Добавь в секцию `services:`:

```yaml
  traefik:
    image: traefik:v3.0
    ports:
      - "8080:80"    # единая точка входа
      - "8081:8080"  # dashboard Traefik
    volumes:
      - ./traefik/traefik.yml:/etc/traefik/traefik.yml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - internal
    depends_on:
      - postgres
      - redis
```

- [ ] **Step 3: Запусти и проверь dashboard**

```bash
docker compose up traefik -d
open http://localhost:8081
```

Ожидаемый результат: открывается Traefik dashboard, видны entrypoints.

- [ ] **Step 4: Commit**

```bash
git add traefik/traefik.yml docker-compose.yml
git commit -m "feat: add Traefik API Gateway on :8080"
```

---

## Фаза 2: Orchestrator

### Task 3: Структура проекта и ORM модели

**Files:**
- Create: `orchestrator/requirements.txt`
- Create: `orchestrator/app/database.py`
- Create: `orchestrator/app/models.py`
- Create: `orchestrator/app/schemas.py`

- [ ] **Step 1: Создай `orchestrator/requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
redis==5.0.4
pydantic==2.7.1
pydantic-settings==2.2.1
httpx==0.27.0
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

- [ ] **Step 2: Создай `orchestrator/app/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 3: Создай `orchestrator/app/models.py`**

```python
from sqlalchemy import String, ForeignKey, DateTime, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum
from .database import Base


class PhoneStatus(str, enum.Enum):
    active = "active"
    banned = "banned"
    warmup = "warmup"
    offline = "offline"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    scheduled = "scheduled"
    running = "running"
    done = "done"
    failed = "failed"


class Phone(Base):
    __tablename__ = "phones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    serial: Mapped[str] = mapped_column(String(64), unique=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    status: Mapped[PhoneStatus] = mapped_column(SAEnum(PhoneStatus), default=PhoneStatus.active)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    warmup_days: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tasks: Mapped[list["ContentTask"]] = relationship(back_populates="phone")


class ContentTask(Base):
    __tablename__ = "content_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("phones.id"))
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    file_url: Mapped[str] = mapped_column(String(512))
    caption: Mapped[str] = mapped_column(String(2200), default="")
    hashtags: Mapped[str] = mapped_column(String(512), default="")   # JSON array as string
    platform: Mapped[str] = mapped_column(String(32), default="tiktok")
    source_service: Mapped[str] = mapped_column(String(64))
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.pending)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    phone: Mapped["Phone"] = relationship(back_populates="tasks")
```

- [ ] **Step 4: Создай `orchestrator/app/schemas.py`**

```python
from pydantic import BaseModel, Field
from uuid import UUID
from typing import Literal


class QueueRequest(BaseModel):
    account_id: UUID
    file_url: str = Field(..., description="MinIO URL видео")
    content_type: Literal["video", "image"] = "video"
    caption: str = ""
    hashtags: list[str] = []
    platform: Literal["tiktok"] = "tiktok"
    source_service: str = Field(..., description="sportzavod | contentzavod")


class QueueResponse(BaseModel):
    task_id: UUID
    scheduled_at: str
    status: str
```

- [ ] **Step 5: Запиши тест (пока просто импорт)**

```python
# orchestrator/tests/test_queue.py
from app.schemas import QueueRequest
import uuid


def test_queue_request_schema():
    req = QueueRequest(
        account_id=uuid.uuid4(),
        file_url="http://minio:9000/content/test.mp4",
        caption="Test",
        hashtags=["test"],
        source_service="sportzavod",
    )
    assert req.platform == "tiktok"
```

- [ ] **Step 6: Запусти тест**

```bash
cd orchestrator
pip install -r requirements.txt
pytest tests/test_queue.py -v
```

Ожидаемый результат: `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add orchestrator/
git commit -m "feat(orchestrator): DB models, Pydantic schemas"
```

---

### Task 4: Redis клиент и очередь задач

**Files:**
- Create: `orchestrator/app/redis_client.py`
- Create: `orchestrator/tests/test_scheduler.py`

- [ ] **Step 1: Напиши тест**

```python
# orchestrator/tests/test_scheduler.py
import pytest
from unittest.mock import AsyncMock
from app.redis_client import RedisQueue


@pytest.mark.asyncio
async def test_push_task():
    mock_redis = AsyncMock()
    mock_redis.lpush = AsyncMock(return_value=1)
    queue = RedisQueue(mock_redis)

    task_id = await queue.push("phone_001", {"file_url": "http://minio/test.mp4"})
    mock_redis.lpush.assert_called_once()
    assert task_id is not None
```

- [ ] **Step 2: Запусти — убедись что FAILED**

```bash
pytest orchestrator/tests/test_scheduler.py -v
```

Ожидаемый результат: `ImportError: cannot import name 'RedisQueue'`

- [ ] **Step 3: Создай `orchestrator/app/redis_client.py`**

```python
import json
import uuid
from redis.asyncio import Redis


class RedisQueue:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _queue_key(self, phone_serial: str) -> str:
        return f"queue:{phone_serial}"

    async def push(self, phone_serial: str, payload: dict) -> str:
        task_id = str(uuid.uuid4())
        item = json.dumps({"task_id": task_id, **payload})
        await self.redis.lpush(self._queue_key(phone_serial), item)
        return task_id

    async def pop(self, phone_serial: str, timeout: int = 0) -> dict | None:
        result = await self.redis.brpop(self._queue_key(phone_serial), timeout=timeout)
        if result is None:
            return None
        _, data = result
        return json.loads(data)

    async def length(self, phone_serial: str) -> int:
        return await self.redis.llen(self._queue_key(phone_serial))
```

- [ ] **Step 4: Запусти тест — должен пройти**

```bash
pytest orchestrator/tests/test_scheduler.py -v
```

Ожидаемый результат: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/app/redis_client.py orchestrator/tests/test_scheduler.py
git commit -m "feat(orchestrator): RedisQueue implementation"
```

---

### Task 5: Smart Scheduler

**Files:**
- Create: `orchestrator/app/scheduler.py`

- [ ] **Step 1: Напиши тесты**

Добавь в `orchestrator/tests/test_scheduler.py`:

```python
from app.scheduler import SmartScheduler
from datetime import datetime, timedelta


def test_new_account_warmup_delay():
    scheduler = SmartScheduler()
    phone = {"warmup_days": 2, "error_count": 0, "timezone": "UTC"}
    delay = scheduler.compute_delay_minutes(phone, last_post_at=None)
    # новый аккаунт (warmup) — минимум 120 минут между постами
    assert delay >= 120


def test_active_account_normal_delay():
    scheduler = SmartScheduler()
    phone = {"warmup_days": 30, "error_count": 0, "timezone": "UTC"}
    delay = scheduler.compute_delay_minutes(phone, last_post_at=None)
    assert 30 <= delay <= 120


def test_high_error_count_increases_delay():
    scheduler = SmartScheduler()
    phone = {"warmup_days": 30, "error_count": 10, "timezone": "UTC"}
    normal = SmartScheduler().compute_delay_minutes(
        {"warmup_days": 30, "error_count": 0, "timezone": "UTC"}, last_post_at=None
    )
    risky = scheduler.compute_delay_minutes(phone, last_post_at=None)
    assert risky > normal
```

- [ ] **Step 2: Запусти — FAILED**

```bash
pytest orchestrator/tests/test_scheduler.py::test_new_account_warmup_delay -v
```

Ожидаемый результат: `ImportError: cannot import name 'SmartScheduler'`

- [ ] **Step 3: Создай `orchestrator/app/scheduler.py`**

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class SmartScheduler:
    BASE_DELAY_MINUTES = 60
    WARMUP_THRESHOLD_DAYS = 14
    WARMUP_DELAY_MINUTES = 180
    ERROR_MULTIPLIER = 15  # +15 минут на каждую ошибку

    def compute_delay_minutes(self, phone: dict, last_post_at: datetime | None) -> int:
        delay = self.BASE_DELAY_MINUTES

        # Warmup phase
        if phone.get("warmup_days", 0) < self.WARMUP_THRESHOLD_DAYS:
            delay = self.WARMUP_DELAY_MINUTES

        # Error penalty
        error_count = phone.get("error_count", 0)
        delay += error_count * self.ERROR_MULTIPLIER

        return delay

    def next_scheduled_at(self, phone: dict, last_post_at: datetime | None) -> datetime:
        delay = self.compute_delay_minutes(phone, last_post_at)
        base = last_post_at or datetime.utcnow()
        return base + timedelta(minutes=delay)
```

- [ ] **Step 4: Запусти все тесты**

```bash
pytest orchestrator/tests/ -v
```

Ожидаемый результат: все `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/app/scheduler.py orchestrator/tests/test_scheduler.py
git commit -m "feat(orchestrator): SmartScheduler with warmup and error penalty"
```

---

### Task 6: FastAPI routes и main.py

**Files:**
- Create: `orchestrator/app/routes/content.py`
- Create: `orchestrator/app/main.py`
- Create: `orchestrator/Dockerfile`

- [ ] **Step 1: Создай `orchestrator/app/routes/content.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from ..database import get_db
from ..models import Phone, ContentTask, TaskStatus
from ..schemas import QueueRequest, QueueResponse
from ..scheduler import SmartScheduler
from ..redis_client import RedisQueue
from redis.asyncio import Redis
import os

router = APIRouter(prefix="/api/content")
scheduler = SmartScheduler()


async def get_redis() -> Redis:
    return Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)


@router.post("/queue", response_model=QueueResponse)
async def queue_content(
    body: QueueRequest,
    db: AsyncSession = Depends(get_db),
):
    # Найти телефон по account_id
    result = await db.execute(select(Phone).where(Phone.account_id == body.account_id))
    phone = result.scalar_one_or_none()
    if phone is None:
        raise HTTPException(status_code=404, detail="Phone not found for account_id")

    # Последняя задача для anti-ban
    last_task_result = await db.execute(
        select(ContentTask)
        .where(ContentTask.phone_id == phone.id, ContentTask.status == TaskStatus.done)
        .order_by(ContentTask.scheduled_at.desc())
        .limit(1)
    )
    last_task = last_task_result.scalar_one_or_none()
    last_post_at = last_task.scheduled_at if last_task else None

    scheduled_at = scheduler.next_scheduled_at(
        {"warmup_days": phone.warmup_days, "error_count": phone.error_count, "timezone": phone.timezone},
        last_post_at=last_post_at,
    )

    task = ContentTask(
        phone_id=phone.id,
        account_id=body.account_id,
        file_url=body.file_url,
        caption=body.caption,
        hashtags=json.dumps(body.hashtags),
        platform=body.platform,
        source_service=body.source_service,
        status=TaskStatus.scheduled,
        scheduled_at=scheduled_at,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    redis = await get_redis()
    queue = RedisQueue(redis)
    await queue.push(phone.serial, {
        "task_id": str(task.id),
        "file_url": body.file_url,
        "caption": body.caption,
        "hashtags": body.hashtags,
        "platform": body.platform,
        "scheduled_at": scheduled_at.isoformat(),
    })

    return QueueResponse(
        task_id=task.id,
        scheduled_at=scheduled_at.isoformat(),
        status=task.status.value,
    )
```

- [ ] **Step 2: Создай `orchestrator/app/main.py`**

```python
from fastapi import FastAPI
from .routes.content import router as content_router
from .database import engine, Base
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Orchestrator", lifespan=lifespan)
app.include_router(content_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 3: Создай `orchestrator/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

- [ ] **Step 4: Добавь orchestrator в `docker-compose.yml`**

Добавь в секцию `services:`:

```yaml
  orchestrator:
    build: ./orchestrator
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres/${POSTGRES_DB}
      REDIS_URL: ${REDIS_URL}
    networks:
      - internal
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.orchestrator.rule=PathPrefix(`/api/content`) || PathPrefix(`/api/phones`)"
      - "traefik.http.services.orchestrator.loadbalancer.server.port=8001"
```

- [ ] **Step 5: Запусти и проверь health**

```bash
docker compose up orchestrator -d --build
curl http://localhost:8080/health
```

Ожидаемый результат: `{"status":"ok"}`

- [ ] **Step 6: Commit**

```bash
git add orchestrator/
git commit -m "feat(orchestrator): FastAPI routes, Dockerfile, Traefik labels"
```

---

## Фаза 3: Workers

### Task 7: ADB Controller

**Files:**
- Create: `workers/requirements.txt`
- Create: `workers/adb_controller.py`
- Create: `workers/tests/test_publisher.py`

- [ ] **Step 1: Создай `workers/requirements.txt`**

```
redis==5.0.4
httpx==0.27.0
pytest==8.2.0
pytest-asyncio==0.23.6
```

- [ ] **Step 2: Напиши тест с моком ADB**

```python
# workers/tests/test_publisher.py
from unittest.mock import patch, MagicMock
from adb_controller import ADBController


def test_tap(tmp_path):
    ctrl = ADBController(serial="emulator-5554")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        ctrl.tap(540, 960)
        mock_run.assert_called_once()
        assert "input" in mock_run.call_args[0][0]


def test_push_file(tmp_path):
    test_file = tmp_path / "video.mp4"
    test_file.write_bytes(b"fake")
    ctrl = ADBController(serial="emulator-5554")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        ctrl.push_file(str(test_file), "/sdcard/video.mp4")
        mock_run.assert_called_once()
        assert "push" in mock_run.call_args[0][0]
```

- [ ] **Step 3: Запусти — FAILED**

```bash
cd workers && pip install -r requirements.txt
pytest tests/test_publisher.py -v
```

Ожидаемый результат: `ImportError: cannot import name 'ADBController'`

- [ ] **Step 4: Создай `workers/adb_controller.py`**

```python
import subprocess
from pathlib import Path


class ADBController:
    def __init__(self, serial: str):
        self.serial = serial

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["adb", "-s", self.serial, *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ADB error: {result.stderr}")
        return result.stdout.strip()

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._run("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def push_file(self, local_path: str, remote_path: str) -> None:
        self._run("push", local_path, remote_path)

    def screenshot(self, local_path: str) -> None:
        self._run("shell", "screencap", "-p", "/sdcard/screen.png")
        self._run("pull", "/sdcard/screen.png", local_path)
```

- [ ] **Step 5: Запусти тесты**

```bash
pytest workers/tests/test_publisher.py -v
```

Ожидаемый результат: `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add workers/
git commit -m "feat(workers): ADBController with tap, swipe, push, screenshot"
```

---

### Task 8: Worker ReAct агент

**Files:**
- Create: `workers/tiktok_publisher.py`
- Create: `workers/worker.py`
- Create: `workers/Dockerfile`

- [ ] **Step 1: Создай `workers/tiktok_publisher.py`**

```python
import time
import tempfile
import httpx
from adb_controller import ADBController


class TikTokPublisher:
    """Публикует видео на TikTok через UI телефона."""

    UPLOAD_BUTTON = (540, 1200)   # координаты кнопки "+" на TikTok
    SELECT_VIDEO = (540, 800)
    NEXT_BUTTON = (950, 120)
    POST_BUTTON = (540, 900)
    CAPTION_FIELD = (540, 400)

    def __init__(self, adb: ADBController):
        self.adb = adb

    def _download_video(self, url: str) -> str:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            with httpx.stream("GET", url) as response:
                for chunk in response.iter_bytes():
                    f.write(chunk)
            return f.name

    def publish(self, file_url: str, caption: str, hashtags: list[str]) -> bool:
        local_path = self._download_video(file_url)
        self.adb.push_file(local_path, "/sdcard/Movies/upload.mp4")

        # Открыть TikTok
        self.adb._run("shell", "am", "start", "-n", "com.zhiliaoapp.musically/.main.MainActivity")
        time.sleep(3)

        # Нажать кнопку "+"
        self.adb.tap(*self.UPLOAD_BUTTON)
        time.sleep(2)

        # Выбрать видео из галереи
        self.adb.tap(*self.SELECT_VIDEO)
        time.sleep(1)
        self.adb.tap(*self.NEXT_BUTTON)
        time.sleep(2)
        self.adb.tap(*self.NEXT_BUTTON)
        time.sleep(2)

        # Ввести caption + hashtags
        full_caption = caption + " " + " ".join(f"#{h}" for h in hashtags)
        self.adb.tap(*self.CAPTION_FIELD)
        self.adb._run("shell", "input", "text", full_caption.replace(" ", "%s"))
        time.sleep(1)

        # Опубликовать
        self.adb.tap(*self.POST_BUTTON)
        time.sleep(3)

        return True
```

- [ ] **Step 2: Создай `workers/worker.py`**

```python
import asyncio
import json
import os
import logging
from datetime import datetime
from redis.asyncio import Redis
from adb_controller import ADBController
from tiktok_publisher import TikTokPublisher

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

PHONE_SERIAL = os.environ["PHONE_SERIAL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


async def report_status(task_id: str, status: str) -> None:
    import httpx
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{ORCHESTRATOR_URL}/api/content/tasks/{task_id}/status",
            json={"status": status},
        )


async def run_worker():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    adb = ADBController(serial=PHONE_SERIAL)
    publisher = TikTokPublisher(adb)
    queue_key = f"queue:{PHONE_SERIAL}"

    log.info(f"Worker started for phone {PHONE_SERIAL}")

    while True:
        result = await redis.brpop(queue_key, timeout=5)
        if result is None:
            continue

        _, raw = result
        task = json.loads(raw)
        task_id = task["task_id"]

        # Ждать scheduled_at
        scheduled_at = datetime.fromisoformat(task["scheduled_at"])
        now = datetime.utcnow()
        if scheduled_at > now:
            wait_seconds = (scheduled_at - now).total_seconds()
            log.info(f"Task {task_id}: waiting {wait_seconds:.0f}s until {scheduled_at}")
            await asyncio.sleep(wait_seconds)

        log.info(f"Task {task_id}: publishing...")
        try:
            publisher.publish(
                file_url=task["file_url"],
                caption=task.get("caption", ""),
                hashtags=task.get("hashtags", []),
            )
            await report_status(task_id, "done")
            log.info(f"Task {task_id}: done")
        except Exception as e:
            log.error(f"Task {task_id} failed: {e}")
            await report_status(task_id, "failed")


if __name__ == "__main__":
    asyncio.run(run_worker())
```

- [ ] **Step 3: Создай `workers/Dockerfile`**

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y android-tools-adb && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "worker.py"]
```

- [ ] **Step 4: Добавь worker в docker-compose.yml**

```yaml
  worker-phone-001:
    build: ./workers
    environment:
      PHONE_SERIAL: ${PHONE_001_SERIAL:-phone_001}
      REDIS_URL: ${REDIS_URL}
      ORCHESTRATOR_URL: http://orchestrator:8001
    networks:
      - internal
    devices:
      - /dev/bus/usb:/dev/bus/usb   # USB-хаб
    depends_on:
      - redis
      - orchestrator
```

- [ ] **Step 5: Commit**

```bash
git add workers/
git commit -m "feat(workers): TikTok publisher, ReAct worker, Dockerfile"
```

---

## Фаза 4: SportZavod

### Task 9: HeyGen + OpenAI интеграция

**Files:**
- Create: `sportzavod/requirements.txt`
- Create: `sportzavod/app/openai_client.py`
- Create: `sportzavod/app/heygen_client.py`
- Create: `sportzavod/app/routes/generate.py`
- Create: `sportzavod/app/main.py`
- Create: `sportzavod/Dockerfile`
- Create: `sportzavod/tests/test_generate.py`

- [ ] **Step 1: Создай `sportzavod/requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
openai==1.30.1
httpx==0.27.0
pydantic==2.7.1
pytest==8.2.0
pytest-asyncio==0.23.6
pytest-mock==3.14.0
```

- [ ] **Step 2: Напиши тесты**

```python
# sportzavod/tests/test_generate.py
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_generate_returns_task_id():
    with patch("app.routes.generate.generate_and_queue") as mock_gen:
        mock_gen.return_value = {"task_id": "abc-123", "status": "queued"}
        async with AsyncClient(app=app, base_url="http://test") as client:
            resp = await client.post("/api/generate", json={
                "account_id": "550e8400-e29b-41d4-a716-446655440000",
                "sport": "basketball",
                "team": "Lakers",
                "event": "win",
            })
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "abc-123"
```

- [ ] **Step 3: Создай `sportzavod/app/openai_client.py`**

```python
import os
from openai import AsyncOpenAI

_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


async def generate_script(sport: str, team: str, event: str) -> str:
    prompt = (
        f"Создай короткий (15-30 сек) спортивный комментарий для TikTok видео. "
        f"Спорт: {sport}. Команда: {team}. Событие: {event}. "
        f"Стиль: энергичный, молодёжный. Только текст, без хэштегов."
    )
    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()
```

- [ ] **Step 4: Создай `sportzavod/app/heygen_client.py`**

```python
import os
import httpx

HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_BASE = "https://api.heygen.com/v2"


async def create_video(script: str, avatar_id: str = "default") -> str:
    """Создаёт видео через HeyGen и возвращает URL файла."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{HEYGEN_BASE}/video/generate",
            headers={"X-Api-Key": HEYGEN_API_KEY, "Content-Type": "application/json"},
            json={
                "video_inputs": [{
                    "character": {"type": "avatar", "avatar_id": avatar_id},
                    "voice": {"type": "text", "input_text": script, "voice_id": "en-US-1"},
                }],
                "dimension": {"width": 1080, "height": 1920},
            },
        )
        resp.raise_for_status()
        video_id = resp.json()["data"]["video_id"]

    # Ждём завершения
    for _ in range(30):
        async with httpx.AsyncClient() as client:
            status_resp = await client.get(
                f"{HEYGEN_BASE}/video/{video_id}",
                headers={"X-Api-Key": HEYGEN_API_KEY},
            )
        data = status_resp.json()["data"]
        if data["status"] == "completed":
            return data["video_url"]
        if data["status"] == "failed":
            raise RuntimeError(f"HeyGen failed: {data.get('error')}")
        import asyncio
        await asyncio.sleep(10)

    raise TimeoutError("HeyGen video generation timed out")
```

- [ ] **Step 5: Создай `sportzavod/app/routes/generate.py`**

```python
from fastapi import APIRouter
from pydantic import BaseModel
from uuid import UUID
import httpx
import os

from ..openai_client import generate_script
from ..heygen_client import create_video

router = APIRouter(prefix="/api")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


class GenerateRequest(BaseModel):
    account_id: UUID
    sport: str
    team: str
    event: str
    hashtags: list[str] = []


async def generate_and_queue(body: GenerateRequest) -> dict:
    script = await generate_script(body.sport, body.team, body.event)
    video_url = await create_video(script)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ORCHESTRATOR_URL}/api/content/queue",
            json={
                "account_id": str(body.account_id),
                "file_url": video_url,
                "content_type": "video",
                "caption": script[:150],
                "hashtags": body.hashtags or [body.sport, body.team.lower()],
                "platform": "tiktok",
                "source_service": "sportzavod",
            },
        )
        resp.raise_for_status()
        return resp.json()


@router.post("/generate")
async def generate(body: GenerateRequest):
    return await generate_and_queue(body)
```

- [ ] **Step 6: Создай `sportzavod/app/main.py`**

```python
from fastapi import FastAPI
from .routes.generate import router

app = FastAPI(title="SportZavod")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Создай `sportzavod/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 8: Добавь в docker-compose.yml**

```yaml
  sportzavod:
    build: ./sportzavod
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      HEYGEN_API_KEY: ${HEYGEN_API_KEY}
      ORCHESTRATOR_URL: http://orchestrator:8001
    networks:
      - internal
    depends_on:
      - orchestrator
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.sportzavod.rule=PathPrefix(`/api/sportzavod`)"
      - "traefik.http.middlewares.sportzavod-strip.stripprefix.prefixes=/api/sportzavod"
      - "traefik.http.routers.sportzavod.middlewares=sportzavod-strip"
      - "traefik.http.services.sportzavod.loadbalancer.server.port=8000"
```

- [ ] **Step 9: Запусти тесты**

```bash
cd sportzavod && pip install -r requirements.txt
pytest tests/test_generate.py -v
```

- [ ] **Step 10: Commit**

```bash
git add sportzavod/
git commit -m "feat(sportzavod): HeyGen + OpenAI video generation"
```

---

## Фаза 5: ContentZavod

### Task 10: Replicate интеграция

**Files:**
- Create: `contentzavod/requirements.txt`
- Create: `contentzavod/app/replicate_client.py`
- Create: `contentzavod/app/routes/generate.py`
- Create: `contentzavod/app/main.py`
- Create: `contentzavod/Dockerfile`

- [ ] **Step 1: Создай `contentzavod/requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
replicate==0.29.0
httpx==0.27.0
pydantic==2.7.1
pytest==8.2.0
pytest-asyncio==0.23.6
```

- [ ] **Step 2: Создай `contentzavod/app/replicate_client.py`**

```python
import os
import replicate

REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")


async def generate_video(prompt: str, duration_seconds: int = 5) -> str:
    """Генерирует видео через Replicate (например, Stable Video Diffusion)."""
    output = replicate.run(
        "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
        input={
            "input_image": prompt,   # или URL картинки
            "frames_per_second": 8,
            "sizing_strategy": "crop_to_16_9",
            "motion_bucket_id": 127,
            "cond_aug": 0.02,
        },
    )
    # output — список URL
    return output[0] if isinstance(output, list) else str(output)
```

- [ ] **Step 3: Создай `contentzavod/app/routes/generate.py`**

```python
from fastapi import APIRouter
from pydantic import BaseModel
from uuid import UUID
import httpx
import os

from ..replicate_client import generate_video

router = APIRouter(prefix="/api")
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001")


class GenerateRequest(BaseModel):
    account_id: UUID
    prompt: str
    caption: str = ""
    hashtags: list[str] = []


@router.post("/generate")
async def generate(body: GenerateRequest):
    video_url = await generate_video(body.prompt)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ORCHESTRATOR_URL}/api/content/queue",
            json={
                "account_id": str(body.account_id),
                "file_url": video_url,
                "content_type": "video",
                "caption": body.caption,
                "hashtags": body.hashtags,
                "platform": "tiktok",
                "source_service": "contentzavod",
            },
        )
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Создай `contentzavod/app/main.py`**

```python
from fastapi import FastAPI
from .routes.generate import router

app = FastAPI(title="ContentZavod")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Создай `contentzavod/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

- [ ] **Step 6: Добавь в docker-compose.yml**

```yaml
  contentzavod:
    build: ./contentzavod
    environment:
      REPLICATE_API_TOKEN: ${REPLICATE_API_TOKEN}
      ORCHESTRATOR_URL: http://orchestrator:8001
    networks:
      - internal
    depends_on:
      - orchestrator
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.contentzavod.rule=PathPrefix(`/api/contentzavod`)"
      - "traefik.http.middlewares.contentzavod-strip.stripprefix.prefixes=/api/contentzavod"
      - "traefik.http.routers.contentzavod.middlewares=contentzavod-strip"
      - "traefik.http.services.contentzavod.loadbalancer.server.port=8002"
```

- [ ] **Step 7: Commit**

```bash
git add contentzavod/
git commit -m "feat(contentzavod): Replicate video generation"
```

---

## Фаза 6: Dashboard API

### Task 11: NestJS API

**Files:**
- Create: `dashboard-api/` (NestJS проект)
- Create: `dashboard-api/Dockerfile`

- [ ] **Step 1: Инициализируй NestJS проект**

```bash
cd dashboard-api
npx @nestjs/cli new . --package-manager npm --skip-git
```

- [ ] **Step 2: Создай `dashboard-api/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package.json .
CMD ["node", "dist/main"]
```

- [ ] **Step 3: Добавь в docker-compose.yml**

```yaml
  dashboard-api:
    build: ./dashboard-api
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres/${POSTGRES_DB}
      JWT_SECRET: ${JWT_SECRET}
      ORCHESTRATOR_URL: http://orchestrator:8001
    networks:
      - internal
    depends_on:
      postgres:
        condition: service_healthy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.dashboard.rule=PathPrefix(`/api/dashboard`)"
      - "traefik.http.middlewares.dashboard-strip.stripprefix.prefixes=/api/dashboard"
      - "traefik.http.routers.dashboard.middlewares=dashboard-strip"
      - "traefik.http.services.dashboard.loadbalancer.server.port=3001"
```

- [ ] **Step 4: Commit**

```bash
git add dashboard-api/
git commit -m "feat(dashboard-api): NestJS app with Traefik routing"
```

---

## Фаза 7: Финальная проверка

### Task 12: Integration smoke test

- [ ] **Step 1: Запусти всю систему**

```bash
docker compose up -d --build
docker compose ps
```

Ожидаемый результат: все сервисы `Up`.

- [ ] **Step 2: Проверь что все сервисы доступны через Gateway**

```bash
curl http://localhost:8080/health                         # orchestrator
curl http://localhost:8080/api/sportzavod/health          # sportzavod (через traefik strip)
curl http://localhost:8080/api/contentzavod/health        # contentzavod
curl http://localhost:8080/api/dashboard/                 # dashboard-api
```

Ожидаемый результат каждого: `{"status":"ok"}` (200)

- [ ] **Step 3: Проверь что прямой доступ по портам недоступен**

```bash
curl http://localhost:8000/health  # должен вернуть Connection refused
curl http://localhost:8001/health  # должен вернуть Connection refused
curl http://localhost:8002/health  # должен вернуть Connection refused
curl http://localhost:3001/        # должен вернуть Connection refused
```

- [ ] **Step 4: Запусти все тесты**

```bash
pytest orchestrator/tests/ -v
pytest sportzavod/tests/ -v
pytest workers/tests/ -v
```

Ожидаемый результат: все `PASSED`.

- [ ] **Step 5: Финальный commit**

```bash
git add .
git commit -m "feat: full system integration — all services behind Traefik Gateway"
```

---

## Итоговая архитектура

```
Client (browser/mobile)
        │
        ▼ :8080
  ┌─────────────┐
  │   Traefik   │  /api/sportzavod/* → sportzavod:8000
  │   Gateway   │  /api/contentzavod/* → contentzavod:8002
  └──────┬──────┘  /api/content/* → orchestrator:8001
         │         /api/dashboard/* → dashboard-api:3001
         │
  internal Docker network
         │
  ┌──────┴──────────────────────────────────┐
  │  sportzavod │ contentzavod │ orchestrator │ dashboard-api │
  └──────────────────────┬──────────────────┘
                         │ Redis queues
                    ┌────▼────┐
                    │ Workers │ → ADB → USB → Телефоны → TikTok
                    └─────────┘
```
