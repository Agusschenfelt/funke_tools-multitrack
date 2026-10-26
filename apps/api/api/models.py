"""SQLAlchemy 2 models. Sections content lives in storage as ``sections.json``."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Timezone-aware datetimes on every backend (SQLite drops the offset)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; use timezone-aware UTC values")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class Job(Base):
    __tablename__ = "jobs"

    # The id is the RQ job id.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    song_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("songs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # analyze | separate | stagepack
    status: Mapped[str] = mapped_column(String(16))  # api.queueing.JobState
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Pack(Base):
    __tablename__ = "packs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    song_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("songs.id", ondelete="CASCADE"), index=True
    )
    # The stagepack job that builds it; ``filename`` is filled when that job finishes.
    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    destination: Mapped[str] = mapped_column(String(16))
    options: Mapped[dict] = mapped_column(JSON)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class SectionsState(Base):
    __tablename__ = "sections_state"

    song_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("songs.id", ondelete="CASCADE"), primary_key=True
    )
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
