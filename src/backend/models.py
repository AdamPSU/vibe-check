"""Domain models for the daily-game generation pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SessionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GameStatus(StrEnum):
    READY = "ready"
    PUBLISHED = "published"


@dataclass(slots=True)
class GenerationSession:
    id: str
    game_id: str
    release_date: str
    status: SessionStatus
    started_at: str
    ended_at: str | None = None
    failure_category: str | None = None
    failure_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


@dataclass(slots=True)
class PublishedGame:
    id: str
    release_date: str
    title: str
    description: str
    status: GameStatus
    source_object_key: str
    build_object_key: str
    screenshot_object_key: str | None
    created_at: str
    published_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"status": self.status.value}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
