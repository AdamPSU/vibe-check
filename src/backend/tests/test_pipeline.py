from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from openai_codex import ApprovalMode, Sandbox

from src.backend.agents import CodexSdkMaker, MakerResult
from src.backend.delivery import validate_delivery
from src.backend.delivery_mcp import validate_delivery as validate_delivery_tool
from src.backend.orchestrator import GenerationOrchestrator
from src.backend.scheduler import DailyGenerationLoop


class FakeMaker:
    def __init__(self, failures: int = 0, malformed_metadata: bool = False) -> None:
        self.failures = failures
        self.malformed_metadata = malformed_metadata
        self.calls = 0

    def generate(self, workspace: Path) -> MakerResult:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("maker failed")
        dist = workspace / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<title>Tiny Orbit</title>", encoding="utf-8")
        metadata = "{" if self.malformed_metadata else json.dumps(
            {"title": "Tiny Orbit", "description": "A small orbital game."}
        )
        (dist / "metadata.json").write_text(metadata, encoding="utf-8")
        return MakerResult("TITLE: This response is ignored", "fake")


class DeliveryTests(unittest.TestCase):
    @staticmethod
    def _package(root: Path, metadata: object | None = None) -> Path:
        dist = root / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
        if metadata is not None:
            (dist / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        return dist

    def test_valid_minimal_and_populated_packages(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = self._package(
                root,
                {"title": "Game", "description": "Description", "extra": True},
            )
            self.assertTrue(validate_delivery(root)["valid"])
            for name in ("game", "assets", "audio"):
                (dist / name).mkdir()
                (dist / name / "file.bin").write_bytes(b"content")
            self.assertTrue(validate_delivery(root)["valid"])

    def test_missing_and_malformed_required_files(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dist").mkdir()
            errors = validate_delivery(root)["errors"]
            self.assertIn("dist/index.html is missing", errors)
            self.assertIn("dist/metadata.json is missing", errors)

            (root / "dist" / "metadata.json").write_text("{", encoding="utf-8")
            self.assertIn("not valid JSON", " ".join(validate_delivery(root)["errors"]))

    def test_metadata_fields_are_nonempty_strings(self) -> None:
        for metadata in (
            {},
            {"title": "", "description": "ok"},
            {"title": "ok", "description": 3},
        ):
            with self.subTest(metadata=metadata), TemporaryDirectory() as temporary:
                root = Path(temporary)
                self._package(root, metadata)
                self.assertFalse(validate_delivery(root)["valid"])

    def test_top_level_names_and_namespace_types_are_enforced(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = self._package(root, {"title": "Game", "description": "Good"})
            (dist / "other.js").touch()
            (dist / "audio").touch()
            errors = validate_delivery(root)["errors"]
            self.assertIn("dist/other.js is not an allowed top-level entry", errors)
            self.assertIn("dist/audio must be a directory", errors)

    def test_mcp_tool_is_bound_to_its_working_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._package(root, {"title": "Game", "description": "Good"})
            with patch("src.backend.delivery_mcp.Path.cwd", return_value=root):
                self.assertTrue(validate_delivery_tool()["valid"])


class PipelineTests(unittest.TestCase):
    def test_generation_uses_file_metadata_and_publishes_trees(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            orchestrator = GenerationOrchestrator(root, FakeMaker())
            with patch("src.backend.delivery.validate_delivery") as validator:
                result = orchestrator.run("2026-07-21")

            validator.assert_not_called()
            self.assertEqual(result.session["status"], "completed")
            self.assertEqual(result.game["title"], "Tiny Orbit")
            self.assertNotEqual(result.game["title"], "This response is ignored")
            self.assertTrue((root / "objects" / result.game["source_object_key"]).is_dir())
            self.assertTrue((root / "objects" / result.game["build_object_key"]).is_dir())

    def test_malformed_metadata_fails_naturally(self) -> None:
        with TemporaryDirectory() as temporary:
            orchestrator = GenerationOrchestrator(
                Path(temporary), FakeMaker(malformed_metadata=True)
            )
            with self.assertRaises(json.JSONDecodeError):
                orchestrator.run("2099-01-01")
            self.assertEqual(orchestrator.catalog.list_sessions()[0]["status"], "failed")

    def test_ready_game_is_hidden_until_promotion(self) -> None:
        with TemporaryDirectory() as temporary:
            orchestrator = GenerationOrchestrator(Path(temporary), FakeMaker())
            release = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            result = orchestrator.run(release, publish=False)
            self.assertEqual(result.game["status"], "ready")
            self.assertIsNone(orchestrator.catalog.get_game(release))
            self.assertEqual(orchestrator.catalog.promote_due(release), 1)
            self.assertEqual(orchestrator.catalog.get_game(release)["status"], "published")

    def test_artifact_only_run_does_not_persist(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            orchestrator = GenerationOrchestrator(root, FakeMaker())
            result = orchestrator.run("2099-01-02", publish=False, persist=False)
            self.assertEqual(result.game["status"], "ready")
            self.assertEqual(orchestrator.catalog.list_sessions(), [])
            self.assertEqual(list((root / "objects").iterdir()), [])

    def test_failed_session_cannot_be_retried(self) -> None:
        with TemporaryDirectory() as temporary:
            orchestrator = GenerationOrchestrator(Path(temporary), FakeMaker(failures=1))
            with self.assertRaisesRegex(RuntimeError, "maker failed"):
                orchestrator.run("2099-01-03")
            with self.assertRaisesRegex(ValueError, "session already exists"):
                orchestrator.run("2099-01-03")
            self.assertEqual(orchestrator.catalog.list_sessions()[0]["status"], "failed")

    def test_scheduler_continues_to_tomorrow_after_today_fails(self) -> None:
        with TemporaryDirectory() as temporary:
            maker = FakeMaker(failures=1)
            orchestrator = GenerationOrchestrator(Path(temporary), maker)
            now = datetime(2026, 7, 21, 12, tzinfo=ZoneInfo("America/New_York"))
            state = DailyGenerationLoop(orchestrator).run_once(now)
            tomorrow = (now.date() + timedelta(days=1)).isoformat()
            self.assertIn(now.date().isoformat(), state["errors"])
            self.assertEqual(orchestrator.catalog.get_scheduled_game(tomorrow)["status"], "ready")
            self.assertEqual(maker.calls, 2)


class CodexSdkMakerTests(unittest.TestCase):
    @staticmethod
    def _event(method: str, payload: dict[str, object]) -> SimpleNamespace:
        model = MagicMock()
        model.model_dump.return_value = payload
        return SimpleNamespace(method=method, payload=model)

    def _codex(self, status: str = "completed") -> tuple[MagicMock, MagicMock]:
        events = [
            self._event(
                "item/completed",
                {
                    "item": {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": "Build complete.",
                    }
                },
            ),
            self._event(
                "turn/completed",
                {
                    "turn": {
                        "status": status,
                        "error": None if status == "completed" else {"message": "SDK failed"},
                    }
                },
            ),
        ]
        turn = MagicMock()
        turn.stream.return_value = iter(events)
        thread = MagicMock()
        thread.turn.return_value = turn
        codex = MagicMock()
        codex.__enter__.return_value = codex
        codex.thread_start.return_value = thread
        return codex, thread

    def test_one_subscription_sdk_turn_with_scoped_configuration(self) -> None:
        codex, thread = self._codex()
        with TemporaryDirectory() as temporary, patch(
            "src.backend.agents.Codex", return_value=codex
        ) as constructor:
            workspace = Path(temporary)
            result = CodexSdkMaker().generate(workspace)

            constructor.assert_called_once()
            sdk_config = constructor.call_args.args[0]
            self.assertIn("agents.max_depth=1", sdk_config.config_overrides)
            self.assertTrue(
                any("adversarial_tester.toml" in value for value in sdk_config.config_overrides)
            )
            kwargs = codex.thread_start.call_args.kwargs
            self.assertEqual(kwargs["model"], "gpt-5.6-luna")
            self.assertEqual(kwargs["config"], {"model_reasoning_effort": "xhigh"})
            self.assertEqual(kwargs["approval_mode"], ApprovalMode.deny_all)
            self.assertEqual(kwargs["sandbox"], Sandbox.workspace_write)
            self.assertTrue(kwargs["ephemeral"])
            self.assertEqual(kwargs["cwd"], str(workspace.resolve()))
            thread.turn.assert_called_once()

            agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
            tester = (workspace / ".codex/agents/adversarial_tester.toml").read_text()
            config = (workspace / ".codex/config.toml").read_text()
            self.assertIn("validate_delivery", agents)
            self.assertIn('model = "gpt-5.6-sol"', tester)
            self.assertIn('sandbox_mode = "read-only"', tester)
            self.assertIn("[mcp_servers.delivery_validator]", config)
            self.assertIn("required = true", config)
            self.assertIn(f"command = {json.dumps(sys.executable)}", config)
            self.assertIn(f"cwd = {json.dumps(str(workspace.resolve()))}", config)
            self.assertEqual(
                [json.loads(line)["method"] for line in (workspace / "codex-events.jsonl").read_text().splitlines()],
                ["item/completed", "turn/completed"],
            )
            self.assertEqual(result.final_response, "Build complete.")
            self.assertEqual(result.provider, "codex-sdk-subscription:gpt-5.6-luna")

    def test_sdk_failure_propagates(self) -> None:
        codex, _ = self._codex("failed")
        with TemporaryDirectory() as temporary, patch(
            "src.backend.agents.Codex", return_value=codex
        ):
            with self.assertRaisesRegex(RuntimeError, "SDK failed"):
                CodexSdkMaker().generate(Path(temporary))


if __name__ == "__main__":
    unittest.main()
