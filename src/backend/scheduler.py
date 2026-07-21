"""24/7 daily release loop for the one-session generation policy."""

from __future__ import annotations

import time
from datetime import datetime, time as clock_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .orchestrator import GenerationOrchestrator


EASTERN = ZoneInfo("America/New_York")


class DailyGenerationLoop:
    def __init__(self, orchestrator: GenerationOrchestrator, timezone: ZoneInfo = EASTERN) -> None:
        self.orchestrator = orchestrator
        self.timezone = timezone

    def run_once(self, now: datetime | None = None) -> dict[str, Any]:
        current = (now or datetime.now(self.timezone)).astimezone(self.timezone)
        today = current.date()
        today_key = today.isoformat()
        promoted = self.orchestrator.catalog.promote_due(today_key)

        current_game = self.orchestrator.catalog.get_game(today_key)
        current_session = self.orchestrator.catalog.has_session_for_release(today_key)
        current_result = None
        if current_game is None and not current_session:
            current_result = self.orchestrator.run(today_key, publish=False)
            promoted += self.orchestrator.catalog.promote_due(today_key)

        next_date = today + timedelta(days=1)
        next_key = next_date.isoformat()
        next_game = self.orchestrator.catalog.get_scheduled_game(next_key)
        next_session = self.orchestrator.catalog.has_session_for_release(next_key)
        next_result = None
        if next_game is None and not next_session:
            next_result = self.orchestrator.run(next_key, publish=False)

        return {
            "date": today_key,
            "promoted": promoted,
            "current_game": current_result.game.to_dict() if current_result else current_game,
            "next_game": next_result.game.to_dict() if next_result else next_game,
            "current_session_exists": current_session or current_result is not None,
            "next_session_exists": next_session or next_result is not None,
        }

    def run_forever(self) -> None:
        while True:
            now = datetime.now(self.timezone)
            self.run_once(now)
            next_day = now.date() + timedelta(days=1)
            wake_at = datetime.combine(next_day, clock_time.min, tzinfo=self.timezone)
            time.sleep(max(1.0, (wake_at - datetime.now(self.timezone)).total_seconds()))
