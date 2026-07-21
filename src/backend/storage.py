"""Local adapters for object storage and catalog metadata.

The interfaces are intentionally filesystem-backed for local development. The
same object keys and record shapes can be backed by S3-compatible storage and
Postgres without changing the orchestrator contract.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from .models import GenerationSession, PublishedGame


def _safe_key(key: str) -> str:
    path = Path(key)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe object key: {key}")
    return path.as_posix()


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        safe = _safe_key(key)
        target = (self.root / safe).resolve()
        target.relative_to(self.root)
        return target

    def put_bytes(self, key: str, content: bytes) -> str:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return _safe_key(key)

    def put_json(self, key: str, value: Any) -> str:
        return self.put_bytes(
            key,
            (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    def put_tree(self, source: Path, prefix: str) -> str:
        source = source.resolve()
        if not source.is_dir():
            raise ValueError(f"source tree does not exist: {source}")
        prefix = _safe_key(prefix)
        destination = self.path_for(prefix)
        destination.mkdir(parents=True, exist_ok=True)
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            if item.is_symlink():
                raise ValueError(f"source tree contains symlink: {relative}")
            target = destination / relative
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
        return prefix

    def exists(self, key: str) -> bool:
        return self.path_for(key).exists()


class LocalCatalogStore:
    """Append-safe JSON metadata adapter used by the local app and tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self.path.exists():
            self._write({"games": {}, "sessions": {}})

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="catalog-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create_session(self, session: GenerationSession) -> None:
        with self._lock:
            data = self._read()
            data["sessions"][session.id] = session.to_dict()
            self._write(data)

    def update_session(self, session: GenerationSession) -> None:
        with self._lock:
            data = self._read()
            data["sessions"][session.id] = session.to_dict()
            self._write(data)

    def publish_game(self, game: PublishedGame) -> None:
        with self._lock:
            data = self._read()
            for existing in data["games"].values():
                if existing["release_date"] == game.release_date:
                    raise ValueError(f"a game is already published for {game.release_date}")
            data["games"][game.id] = game.to_dict()
            self._write(data)

    def list_games(self, include_unpublished: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            games = list(data["games"].values())
            if not include_unpublished:
                today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
                games = [
                    game
                    for game in games
                    if game["status"] == "published" and game["release_date"] <= today
                ]
            return sorted(
                games,
                key=lambda game: game["release_date"],
                reverse=True,
            )

    def get_game(self, release_date: str) -> dict[str, Any] | None:
        return next(
            (game for game in self.list_games() if game["release_date"] == release_date),
            None,
        )

    def get_scheduled_game(self, release_date: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._read()
            return next(
                (
                    game
                    for game in data["games"].values()
                    if game["release_date"] == release_date
                ),
                None,
            )

    def promote_due(self, through_date: str) -> int:
        with self._lock:
            data = self._read()
            promoted = 0
            now = datetime.now(timezone.utc).isoformat()
            for game in data["games"].values():
                if game["status"] == "ready" and game["release_date"] <= through_date:
                    game["status"] = "published"
                    game["published_at"] = now
                    promoted += 1
            if promoted:
                self._write(data)
            return promoted

    def has_session_for_release(self, release_date: str) -> bool:
        with self._lock:
            data = self._read()
            return any(
                session["release_date"] == release_date
                for session in data["sessions"].values()
            )

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            data = self._read()
            return sorted(
                data["sessions"].values(),
                key=lambda session: session["started_at"],
                reverse=True,
            )


class PostgresCatalogStore:
    """Postgres metadata adapter for the hosted deployment.

    The import is deferred so the credential-free local mode does not require
    a running database or the optional psycopg package.
    """

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised in hosted mode
            raise RuntimeError(
                "Postgres mode requires the optional 'postgres' dependency"
            ) from exc
        self._connection = psycopg.connect(dsn, autocommit=True)
        self._lock = Lock()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS generation_sessions (
                    id TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL,
                    release_date DATE NOT NULL,
                    status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    ended_at TIMESTAMPTZ,
                    failure_category TEXT,
                    failure_summary TEXT
                );
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY,
                    release_date DATE NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_object_key TEXT NOT NULL,
                    build_object_key TEXT NOT NULL,
                    screenshot_object_key TEXT,
                    created_at TIMESTAMPTZ NOT NULL,
                    published_at TIMESTAMPTZ NOT NULL
                );
                """
            )

    def create_session(self, session: GenerationSession) -> None:
        self.update_session(session)

    def update_session(self, session: GenerationSession) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO generation_sessions
                  (id, game_id, release_date, status, started_at, ended_at,
                   failure_category, failure_summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  status = EXCLUDED.status,
                  ended_at = EXCLUDED.ended_at,
                  failure_category = EXCLUDED.failure_category,
                  failure_summary = EXCLUDED.failure_summary
                """,
                (
                    session.id,
                    session.game_id,
                    session.release_date,
                    session.status.value,
                    session.started_at,
                    session.ended_at,
                    session.failure_category,
                    session.failure_summary,
                ),
            )

    def publish_game(self, game: PublishedGame) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO games
                  (id, release_date, title, description, status,
                   source_object_key, build_object_key, screenshot_object_key,
                   created_at, published_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    game.id,
                    game.release_date,
                    game.title,
                    game.description,
                    game.status.value,
                    game.source_object_key,
                    game.build_object_key,
                    game.screenshot_object_key,
                    game.created_at,
                    game.published_at,
                ),
            )

    @staticmethod
    def _game_row(row: tuple[Any, ...]) -> dict[str, Any]:
        fields = (
            "id",
            "release_date",
            "title",
            "description",
            "status",
            "source_object_key",
            "build_object_key",
            "screenshot_object_key",
            "created_at",
            "published_at",
        )
        result = dict(zip(fields, row))
        for field in ("release_date", "created_at", "published_at"):
            if result[field] is not None:
                result[field] = result[field].isoformat()
        return result

    def list_games(self, include_unpublished: bool = False) -> list[dict[str, Any]]:
        with self._lock, self._connection.cursor() as cursor:
            query = (
                "SELECT id, release_date, title, description, status, source_object_key, "
                "build_object_key, screenshot_object_key, created_at, published_at "
                "FROM games "
            )
            if not include_unpublished:
                today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
                query += "WHERE status = 'published' AND release_date <= %s "
            query += "ORDER BY release_date DESC"
            cursor.execute(query, (today,) if not include_unpublished else ())
            return [self._game_row(row) for row in cursor.fetchall()]

    def get_game(self, release_date: str) -> dict[str, Any] | None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, release_date, title, description, status, source_object_key, "
                "build_object_key, screenshot_object_key, created_at, published_at "
                "FROM games WHERE release_date = %s",
                (release_date,),
            )
            row = cursor.fetchone()
            return self._game_row(row) if row else None

    def get_scheduled_game(self, release_date: str) -> dict[str, Any] | None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, release_date, title, description, status, source_object_key, "
                "build_object_key, screenshot_object_key, created_at, published_at "
                "FROM games WHERE release_date = %s",
                (release_date,),
            )
            row = cursor.fetchone()
            return self._game_row(row) if row else None

    def promote_due(self, through_date: str) -> int:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE games SET status = 'published', published_at = NOW() "
                "WHERE status = 'ready' AND release_date <= %s",
                (through_date,),
            )
            return cursor.rowcount

    def has_session_for_release(self, release_date: str) -> bool:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM generation_sessions WHERE release_date = %s LIMIT 1",
                (release_date,),
            )
            return cursor.fetchone() is not None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, game_id, release_date, status, started_at, ended_at, "
                "failure_category, failure_summary FROM generation_sessions "
                "ORDER BY started_at DESC"
            )
            fields = (
                "id",
                "game_id",
                "release_date",
                "status",
                "started_at",
                "ended_at",
                "failure_category",
                "failure_summary",
            )
            return [
                {
                    key: value.isoformat() if hasattr(value, "isoformat") else value
                    for key, value in zip(fields, row)
                }
                for row in cursor.fetchall()
            ]

    def close(self) -> None:
        self._connection.close()
