"""Local development storage and the production Postgres catalog."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")
Record = dict[str, Any]


class LocalCatalogStore:
    """Small atomic JSON catalog used by local runs and tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not path.exists():
            self._write({"sessions": {}, "games": {}})

    def _read(self) -> Record:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: Record) -> None:
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix="catalog-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def claim_session(self, session: Record) -> None:
        release = session["release_date"]
        with self._lock:
            data = self._read()
            if release in data["sessions"]:
                raise ValueError(f"a generation session already exists for {release}")
            data["sessions"][release] = session
            self._write(data)

    def update_session(self, session: Record) -> None:
        with self._lock:
            data = self._read()
            data["sessions"][session["release_date"]] = session
            self._write(data)

    def save_game(self, game: Record) -> None:
        release = game["release_date"]
        with self._lock:
            data = self._read()
            if release in data["games"]:
                raise ValueError(f"a game already exists for {release}")
            data["games"][release] = game
            self._write(data)

    def list_games(self) -> list[Record]:
        today = datetime.now(EASTERN).date().isoformat()
        with self._lock:
            games = self._read()["games"].values()
            visible = [
                game
                for game in games
                if game["status"] == "published" and game["release_date"] <= today
            ]
        return sorted(visible, key=lambda game: game["release_date"], reverse=True)

    def get_game(self, release_date: str) -> Record | None:
        today = datetime.now(EASTERN).date().isoformat()
        with self._lock:
            game = self._read()["games"].get(release_date)
        if game and game["status"] == "published" and release_date <= today:
            return game
        return None

    def get_scheduled_game(self, release_date: str) -> Record | None:
        with self._lock:
            return self._read()["games"].get(release_date)

    def has_session_for_release(self, release_date: str) -> bool:
        with self._lock:
            return release_date in self._read()["sessions"]

    def list_sessions(self) -> list[Record]:
        with self._lock:
            sessions = list(self._read()["sessions"].values())
        return sorted(sessions, key=lambda session: session["started_at"], reverse=True)

    def promote_due(self, through_date: str) -> int:
        with self._lock:
            data = self._read()
            due = [
                game
                for game in data["games"].values()
                if game["status"] == "ready" and game["release_date"] <= through_date
            ]
            now = datetime.now(timezone.utc).isoformat()
            for game in due:
                game.update(status="published", published_at=now)
            if due:
                self._write(data)
            return len(due)

    def fail_running_sessions(self, summary: str) -> int:
        with self._lock:
            data = self._read()
            running = [
                session
                for session in data["sessions"].values()
                if session["status"] == "running"
            ]
            now = datetime.now(timezone.utc).isoformat()
            for session in running:
                session.update(
                    status="failed",
                    ended_at=now,
                    failure_category="worker_restart",
                    failure_summary=summary,
                )
            if running:
                self._write(data)
            return len(running)


class PostgresCatalogStore:
    """Postgres implementation with release-date uniqueness as the durable claim."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("install the backend's postgres extra") from exc
        self._connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self._lock = Lock()
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS generation_sessions (
                    id TEXT PRIMARY KEY, game_id TEXT NOT NULL,
                    release_date DATE NOT NULL UNIQUE, status TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ,
                    failure_category TEXT, failure_summary TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY, release_date DATE NOT NULL UNIQUE,
                    title TEXT NOT NULL, description TEXT NOT NULL, status TEXT NOT NULL,
                    source_object_key TEXT NOT NULL, build_object_key TEXT NOT NULL,
                    screenshot_object_key TEXT, created_at TIMESTAMPTZ NOT NULL,
                    published_at TIMESTAMPTZ
                )
                """
            )
            cursor.execute("ALTER TABLE games ALTER COLUMN published_at DROP NOT NULL")

    @staticmethod
    def _clean(row: Record | None) -> Record | None:
        if row is None:
            return None
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in row.items()
        }

    def claim_session(self, session: Record) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO generation_sessions VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(session[key] for key in (
                    "id", "game_id", "release_date", "status", "started_at", "ended_at",
                    "failure_category", "failure_summary",
                )),
            )

    def update_session(self, session: Record) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE generation_sessions SET status=%s, ended_at=%s,
                    failure_category=%s, failure_summary=%s WHERE release_date=%s
                """,
                (
                    session["status"], session["ended_at"], session["failure_category"],
                    session["failure_summary"], session["release_date"],
                ),
            )

    def save_game(self, game: Record) -> None:
        fields = (
            "id", "release_date", "title", "description", "status", "source_object_key",
            "build_object_key", "screenshot_object_key", "created_at", "published_at",
        )
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO games VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(game[field] for field in fields),
            )

    def list_games(self) -> list[Record]:
        today = datetime.now(EASTERN).date().isoformat()
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM games WHERE status='published' AND release_date <= %s "
                "ORDER BY release_date DESC",
                (today,),
            )
            return [self._clean(row) for row in cursor.fetchall()]  # type: ignore[misc]

    def _game(self, release_date: str, published_only: bool) -> Record | None:
        where = "release_date=%s" + (" AND status='published'" if published_only else "")
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM games WHERE {where}", (release_date,))
            return self._clean(cursor.fetchone())

    def get_game(self, release_date: str) -> Record | None:
        return self._game(release_date, published_only=True)

    def get_scheduled_game(self, release_date: str) -> Record | None:
        return self._game(release_date, published_only=False)

    def has_session_for_release(self, release_date: str) -> bool:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM generation_sessions WHERE release_date=%s", (release_date,)
            )
            return cursor.fetchone() is not None

    def list_sessions(self) -> list[Record]:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute("SELECT * FROM generation_sessions ORDER BY started_at DESC")
            return [self._clean(row) for row in cursor.fetchall()]  # type: ignore[misc]

    def promote_due(self, through_date: str) -> int:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE games SET status='published', published_at=NOW() "
                "WHERE status='ready' AND release_date <= %s",
                (through_date,),
            )
            return cursor.rowcount

    def fail_running_sessions(self, summary: str) -> int:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE generation_sessions SET status='failed', ended_at=NOW(), "
                "failure_category='worker_restart', failure_summary=%s WHERE status='running'",
                (summary,),
            )
            return cursor.rowcount
