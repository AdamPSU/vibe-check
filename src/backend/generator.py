"""CLI entry point for a single local generation session."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from .agents import ChromeTester, CodexCliMaker, CodexCliTester, DemoGameMaker
from .orchestrator import GenerationOrchestrator
from .scheduler import DailyGenerationLoop
from .storage import PostgresCatalogStore


def build_orchestrator(data_dir: Path, mode: str) -> GenerationOrchestrator:
    if mode == "demo":
        maker = DemoGameMaker()
        tester = ChromeTester()
    elif mode == "codex":
        maker = CodexCliMaker()
        tester = CodexCliTester()
    else:
        raise ValueError(f"unsupported mode: {mode}")
    database_url = os.getenv("VIBE_CHECK_DATABASE_URL")
    catalog = PostgresCatalogStore(database_url) if database_url else None
    return GenerationOrchestrator(data_dir, maker, tester, catalog=catalog)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one daily-game generation session")
    parser.add_argument("--date", dest="release_date", help="release date in YYYY-MM-DD")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="run the continuous America/New_York daily scheduler",
    )
    parser.add_argument(
        "--mode",
        choices=("demo", "codex"),
        default="demo",
        help="demo runs credential-free local maker/tester adapters; codex invokes the installed Codex CLI",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("var/daily-games"))
    args = parser.parse_args()
    orchestrator = build_orchestrator(args.data_dir, args.mode)
    if args.loop:
        DailyGenerationLoop(orchestrator).run_forever()
        return 0
    if not args.release_date:
        parser.error("--date is required unless --loop is used")
    date.fromisoformat(args.release_date)
    result = orchestrator.run(args.release_date)
    print(
        json.dumps(
            {
                "session_id": result.session.id,
                "game_id": result.game.id,
                "release_date": result.game.release_date,
                "title": result.game.title,
                "description": result.game.description,
                "artifact_sha256": result.artifact.sha256,
                "browser_ok": result.tester.browser.ok,
                "object_store": str(args.data_dir / "objects"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
