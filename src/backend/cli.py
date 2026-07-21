"""CLI for one subscription-backed generation session or the daily worker."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from .data.catalog import PostgresCatalogStore
from .generation.codex import CodexSdkMaker
from .generation.pipeline import GenerationOrchestrator
from .generation.scheduler import DailyGenerationLoop


def build_orchestrator(data_dir: Path, smoke_test: bool = False) -> GenerationOrchestrator:
    dsn = os.getenv("VIBE_CHECK_DATABASE_URL")
    catalog = PostgresCatalogStore(dsn) if dsn else None
    return GenerationOrchestrator(
        data_dir,
        CodexSdkMaker(smoke_test=smoke_test),
        catalog=catalog,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily games with Codex")
    parser.add_argument("--date", dest="release_date", help="release date in YYYY-MM-DD")
    parser.add_argument("--loop", action="store_true", help="run the daily worker")
    parser.add_argument("--data-dir", type=Path, default=Path("var/daily-games"))
    parser.add_argument(
        "--artifact-only",
        action="store_true",
        help="generate locally without catalog or object-store writes",
    )
    parser.add_argument(
        "--real-smoke",
        action="store_true",
        help="explicitly exercise Exa, Lyria, and Chrome in an artifact-only run",
    )
    args = parser.parse_args()
    if args.real_smoke and not args.artifact_only:
        parser.error("--real-smoke requires --artifact-only")

    orchestrator = build_orchestrator(args.data_dir, smoke_test=args.real_smoke)
    if args.loop:
        DailyGenerationLoop(orchestrator).run_forever()
        return 0
    if not args.release_date:
        parser.error("--date is required unless --loop is used")
    date.fromisoformat(args.release_date)

    result = orchestrator.run(
        args.release_date,
        publish=not args.artifact_only,
        persist=not args.artifact_only,
    )
    print(
        json.dumps(
            {
                "session_id": result.session["id"],
                "game_id": result.game["id"],
                "release_date": result.game["release_date"],
                "title": result.game["title"],
                "description": result.game["description"],
                "artifact_only": args.artifact_only,
                "workspace": str(result.workspace),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
