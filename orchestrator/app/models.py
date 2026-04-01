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
    hashtags: Mapped[str] = mapped_column(String(512), default="")
    platform: Mapped[str] = mapped_column(String(32), default="tiktok")
    source_service: Mapped[str] = mapped_column(String(64))
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.pending)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    phone: Mapped["Phone"] = relationship(back_populates="tasks")
