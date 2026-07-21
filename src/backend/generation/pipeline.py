"""One Codex session from durable claim through publication."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..data.catalog import LocalCatalogStore, Record
from ..data.objects import LocalObjectStore
from .codex import GameMaker


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class PipelineResult:
    session: Record
    game: Record
    workspace: Path


class GenerationOrchestrator:
    def __init__(
        self,
        root: Path,
        maker: GameMaker,
        catalog: Any | None = None,
        objects: LocalObjectStore | None = None,
    ) -> None:
        self.root = root.resolve()
        self.maker = maker
        self.catalog = catalog or LocalCatalogStore(self.root / "catalog.json")
        self.objects = objects or LocalObjectStore(self.root / "objects")
        self.workspaces = self.root / "workspaces"
        self.events = self.root / "events.jsonl"
        self.workspaces.mkdir(parents=True, exist_ok=True)

    def _event(self, session_id: str, event_type: str, **payload: Any) -> None:
        event = {
            "session_id": session_id,
            "event_type": event_type,
            "occurred_at": utc_now(),
            "payload": payload,
        }
        with self.events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def run(
        self,
        release_date: str,
        publish: bool = True,
        persist: bool = True,
    ) -> PipelineResult:
        session_id = uuid.uuid4().hex
        game_id = uuid.uuid4().hex
        workspace = self.workspaces / session_id
        workspace.mkdir()
        session: Record = {
            "id": session_id,
            "game_id": game_id,
            "release_date": release_date,
            "status": "running",
            "started_at": utc_now(),
            "ended_at": None,
            "failure_category": None,
            "failure_summary": None,
        }
        if persist:
            if self.catalog.get_scheduled_game(release_date):
                raise ValueError(f"a game already exists for {release_date}")
            self.catalog.claim_session(session)
        self._event(session_id, "session.started", release_date=release_date)

        try:
            final_response = self.maker.generate(workspace)
            (workspace / "maker-final-response.txt").write_text(
                final_response, encoding="utf-8"
            )
            metadata = json.loads(
                (workspace / "dist" / "metadata.json").read_text(encoding="utf-8")
            )
            title, description = metadata["title"], metadata["description"]

            source_key = build_key = ""
            if persist:
                source_key = self.objects.put_tree(workspace, f"{game_id}/source")
                build_key = self.objects.put_tree(workspace / "dist", f"{game_id}/build")
            game: Record = {
                "id": game_id,
                "release_date": release_date,
                "title": title,
                "description": description,
                "status": "published" if publish else "ready",
                "source_object_key": source_key,
                "build_object_key": build_key,
                "screenshot_object_key": None,
                "created_at": session["started_at"],
                "published_at": utc_now() if publish else None,
            }
            if persist:
                self.catalog.save_game(game)
            session.update(status="completed", ended_at=utc_now())
            if persist:
                self.catalog.update_session(session)
            self._event(session_id, "game.ready", game_id=game_id, status=game["status"])
            return PipelineResult(session, game, workspace)
        except Exception as exc:
            session.update(
                status="failed",
                ended_at=utc_now(),
                failure_category=type(exc).__name__,
                failure_summary=str(exc),
            )
            if persist:
                self.catalog.update_session(session)
            self._event(session_id, "session.failed", error=str(exc))
            raise
