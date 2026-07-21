"""Daily worker loop in the product's release timezone."""

from __future__ import annotations

import time
from datetime import datetime, time as clock_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .pipeline import GenerationOrchestrator


EASTERN = ZoneInfo("America/New_York")


class DailyGenerationLoop:
    def __init__(self, orchestrator: GenerationOrchestrator) -> None:
        self.orchestrator = orchestrator
        self.reconciled = False

    def run_once(self, now: datetime | None = None) -> dict[str, Any]:
        if not self.reconciled:
            self.orchestrator.catalog.fail_running_sessions(
                "generation worker restarted before the session completed"
            )
            self.reconciled = True

        current = (now or datetime.now(EASTERN)).astimezone(EASTERN)
        today = current.date()
        releases = (today, today + timedelta(days=1))
        state: dict[str, Any] = {
            "date": today.isoformat(),
            "promoted": self.orchestrator.catalog.promote_due(today.isoformat()),
            "generated": {},
            "errors": {},
        }
        for release in releases:
            key = release.isoformat()
            if self.orchestrator.catalog.get_scheduled_game(key):
                continue
            if self.orchestrator.catalog.has_session_for_release(key):
                continue
            try:
                result = self.orchestrator.run(key, publish=False)
                state["generated"][key] = result.game
                if release == today:
                    state["promoted"] += self.orchestrator.catalog.promote_due(key)
            except Exception as exc:
                state["errors"][key] = str(exc)
        return state

    def run_forever(self) -> None:
        while True:
            now = datetime.now(EASTERN)
            self.run_once(now)
            midnight = datetime.combine(
                now.date() + timedelta(days=1), clock_time.min, tzinfo=EASTERN
            )
            time.sleep(max(1, (midnight - datetime.now(EASTERN)).total_seconds()))
