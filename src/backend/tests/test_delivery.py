from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.backend.delivery.contract import validate_delivery
from src.backend.delivery.mcp import validate_delivery as validate_delivery_tool


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
            with patch("src.backend.delivery.mcp.Path.cwd", return_value=root):
                self.assertTrue(validate_delivery_tool()["valid"])
