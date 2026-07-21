from __future__ import annotations

import shutil
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from src.backend.agents import ChromeTester, DemoGameMaker
from src.backend.artifacts import validate_build
from src.backend.metadata import MetadataError, parse_game_metadata
from src.backend.orchestrator import GenerationOrchestrator
from src.backend.prompts import ADVERSARIAL_TESTER_SYSTEM_PROMPT, MAKER_SYSTEM_PROMPT


class PipelineTests(unittest.TestCase):
    def test_metadata_contract(self) -> None:
        metadata = parse_game_metadata("TITLE: Tiny Orbit\nDESCRIPTION: A small game.")
        self.assertEqual(metadata.title, "Tiny Orbit")
        self.assertEqual(metadata.description, "A small game.")
        with self.assertRaises(MetadataError):
            parse_game_metadata("TITLE: Missing description")

    def test_artifact_rejects_external_resources(self) -> None:
        with TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            (dist / "index.html").write_text(
                '<script src="https://example.com/game.js"></script>', encoding="utf-8"
            )
            report = validate_build(dist)
            self.assertFalse(report.ok)
            self.assertIn("https://example.com/game.js", report.external_resources)

    def test_end_to_end_generation_publishes_and_retains_evidence(self) -> None:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if not chrome.is_file() and not shutil.which("google-chrome") and not shutil.which("chromium"):
            self.skipTest("desktop Chrome is not installed")

        with TemporaryDirectory() as tmp:
            result = GenerationOrchestrator(
                Path(tmp), DemoGameMaker(), ChromeTester()
            ).run("2026-07-21")
            self.assertEqual(result.session.status.value, "completed")
            self.assertEqual(result.game.title, "Button Bloom")
            self.assertTrue(result.tester.browser.ok)
            self.assertTrue(result.tester.browser.finished)
            self.assertTrue(result.tester.browser.data["replay_reset_observed"])
            self.assertTrue(result.tester.browser.data["screenshot"])
            self.assertTrue(result.tester.browser.data["screenshot_surface"])
            self.assertTrue((Path(tmp) / "objects" / result.game.build_object_key).is_dir())
            self.assertEqual(len(GenerationOrchestrator(Path(tmp), DemoGameMaker(), ChromeTester()).catalog.list_games()), 1)

    def test_ready_game_is_hidden_until_promotion(self) -> None:
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        if not chrome.is_file() and not shutil.which("google-chrome") and not shutil.which("chromium"):
            self.skipTest("desktop Chrome is not installed")

        with TemporaryDirectory() as tmp:
            orchestrator = GenerationOrchestrator(Path(tmp), DemoGameMaker(), ChromeTester())
            release_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            result = orchestrator.run(release_date, publish=False)
            self.assertEqual(result.game.status.value, "ready")
            self.assertIsNone(orchestrator.catalog.get_game(release_date))
            self.assertEqual(orchestrator.catalog.promote_due(release_date), 1)
            self.assertEqual(orchestrator.catalog.get_game(release_date)["status"], "published")

    def test_prompts_are_loaded_from_package_files(self) -> None:
        self.assertIn("TITLE:", MAKER_SYSTEM_PROMPT)
        self.assertIn("read-only", ADVERSARIAL_TESTER_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
