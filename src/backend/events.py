"""Append-only generation event journal."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


class EventJournal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def append(self, session_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        event = {
            "session_id": session_id,
            "event_type": event_type,
            "occurred_at": datetime.now().astimezone().isoformat(),
            "payload": payload or {},
        }
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
