"""One-session generation, review, validation, and publication workflow."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agents import GameMaker, GameTester, TesterResult
from .artifacts import ArtifactReport, validate_build
from .events import EventJournal
from .metadata import GameMetadata, parse_game_metadata
from .models import GameStatus, GenerationSession, PublishedGame, SessionStatus, utc_now
from .storage import LocalCatalogStore, LocalObjectStore


class GenerationFailure(RuntimeError):
    def __init__(self, session_id: str, message: str) -> None:
        super().__init__(message)
        self.session_id = session_id


@dataclass(slots=True)
class PipelineResult:
    session: GenerationSession
    game: PublishedGame
    artifact: ArtifactReport
    tester: TesterResult
    workspace: Path


class GenerationOrchestrator:
    def __init__(
        self,
        root: Path,
        maker: GameMaker,
        tester: GameTester,
        catalog: Any | None = None,
        objects: LocalObjectStore | None = None,
    ) -> None:
        self.root = root.resolve()
        self.maker = maker
        self.tester = tester
        self.workspaces = self.root / "workspaces"
        self.evidence = self.root / "evidence"
        self.objects = objects or LocalObjectStore(self.root / "objects")
        self.catalog = catalog or LocalCatalogStore(self.root / "catalog.json")
        self.events = EventJournal(self.root / "events.jsonl")
        self.workspaces.mkdir(parents=True, exist_ok=True)
        self.evidence.mkdir(parents=True, exist_ok=True)

    def run(self, release_date: str, publish: bool = True) -> PipelineResult:
        if self.catalog.get_scheduled_game(release_date):
            raise ValueError(f"a game is already scheduled for {release_date}")

        session_id = uuid.uuid4().hex
        game_id = uuid.uuid4().hex
        workspace = self.workspaces / session_id
        evidence_dir = self.evidence / session_id
        workspace.mkdir(parents=True)
        session = GenerationSession(
            id=session_id,
            game_id=game_id,
            release_date=release_date,
            status=SessionStatus.RUNNING,
            started_at=utc_now(),
        )
        self.catalog.create_session(session)
        self.events.append(session_id, "session.started", {"release_date": release_date})

        try:
            self.events.append(session_id, "maker.started")
            maker_result = self.maker.generate(workspace)
            (workspace / "maker-final-response.txt").write_text(
                maker_result.final_response, encoding="utf-8"
            )
            self.events.append(session_id, "maker.completed", {"provider": maker_result.provider})

            initial_artifact = validate_build(workspace / "dist")
            self.events.append(
                session_id,
                "artifact.initial_validation",
                {"ok": initial_artifact.ok, "summary": initial_artifact.summary()},
            )
            if not initial_artifact.ok:
                raise GenerationFailure(session_id, initial_artifact.summary())

            self.events.append(session_id, "tester.started", {"label": "initial"})
            initial_tester = self.tester.inspect(workspace, evidence_dir, "initial")
            self.events.append(
                session_id,
                "tester.completed",
                {"label": "initial", "ok": initial_tester.browser.ok},
            )

            self.events.append(session_id, "maker.repair_started")
            repair_result = self.maker.repair(workspace, initial_tester.report)
            (workspace / "maker-repair-response.txt").write_text(
                repair_result.final_response, encoding="utf-8"
            )
            self.events.append(session_id, "maker.repair_completed", {"provider": repair_result.provider})

            final_artifact = validate_build(workspace / "dist")
            self.events.append(
                session_id,
                "artifact.final_validation",
                {"ok": final_artifact.ok, "summary": final_artifact.summary()},
            )
            if not final_artifact.ok:
                raise GenerationFailure(session_id, final_artifact.summary())

            self.events.append(session_id, "tester.started", {"label": "final"})
            final_tester = self.tester.inspect(workspace, evidence_dir, "final")
            self.events.append(
                session_id,
                "tester.completed",
                {"label": "final", "ok": final_tester.browser.ok},
            )
            if not final_tester.browser.ok:
                raise GenerationFailure(session_id, final_tester.browser.report())

            metadata = parse_game_metadata(repair_result.final_response)
            game = self._publish(
                session=session,
                metadata=metadata,
                workspace=workspace,
                evidence_dir=evidence_dir,
                artifact=final_artifact,
                tester=final_tester,
                publish=publish,
            )
            session.status = SessionStatus.COMPLETED
            session.ended_at = utc_now()
            self.catalog.update_session(session)
            self.events.append(
                session_id,
                "game.published" if publish else "game.ready",
                {"game_id": game.id},
            )
            return PipelineResult(
                session=session,
                game=game,
                artifact=final_artifact,
                tester=final_tester,
                workspace=workspace,
            )
        except GenerationFailure as exc:
            self._fail(session, "validation", str(exc))
            raise
        except Exception as exc:
            self._fail(session, type(exc).__name__, str(exc))
            raise GenerationFailure(session_id, str(exc)) from exc

    def _publish(
        self,
        session: GenerationSession,
        metadata: GameMetadata,
        workspace: Path,
        evidence_dir: Path,
        artifact: ArtifactReport,
        tester: TesterResult,
        publish: bool,
    ) -> PublishedGame:
        source_key = self.objects.put_tree(workspace, f"{session.game_id}/source")
        build_key = self.objects.put_tree(workspace / "dist", f"{session.game_id}/build")
        screenshot_path = tester.browser.data.get("screenshot")
        screenshot_key = None
        if screenshot_path and Path(screenshot_path).is_file():
            screenshot_key = self.objects.put_bytes(
                f"{session.game_id}/screenshots/game.png",
                Path(screenshot_path).read_bytes(),
            )
        self.objects.put_json(
            f"{session.game_id}/reports/final.json",
            {
                "artifact": {
                    "ok": artifact.ok,
                    "total_bytes": artifact.total_bytes,
                    "sha256": artifact.sha256,
                },
                "browser": tester.browser.data,
                "tester_report": tester.report,
            },
        )
        game = PublishedGame(
            id=session.game_id,
            release_date=session.release_date,
            title=metadata.title,
            description=metadata.description,
            status=GameStatus.PUBLISHED if publish else GameStatus.READY,
            source_object_key=source_key,
            build_object_key=build_key,
            screenshot_object_key=screenshot_key,
            created_at=session.started_at,
            published_at=utc_now() if publish else None,
        )
        self.catalog.publish_game(game)
        return game

    def _fail(self, session: GenerationSession, category: str, summary: str) -> None:
        session.status = SessionStatus.FAILED
        session.ended_at = utc_now()
        session.failure_category = category
        session.failure_summary = summary
        self.catalog.update_session(session)
        self.events.append(
            session.id,
            "session.failed",
            {"failure_category": category, "failure_summary": summary},
        )
