"""The game package contract exposed to Codex through MCP."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ALLOWED_ENTRIES = {"index.html", "metadata.json", "game", "assets", "audio"}
OPTIONAL_DIRECTORIES = {"game", "assets", "audio"}


def validate_delivery(workspace: Path) -> dict[str, Any]:
    """Validate the final package rooted at ``workspace/dist``."""

    dist = workspace / "dist"
    checked = ["dist/index.html", "dist/metadata.json"]
    if not dist.is_dir():
        return {"valid": False, "errors": ["dist/ is missing"], "checked": checked}

    errors = [
        f"dist/{entry.name} is not an allowed top-level entry"
        for entry in dist.iterdir()
        if entry.name not in ALLOWED_ENTRIES
    ]
    errors.extend(
        f"dist/{name} must be a directory"
        for name in OPTIONAL_DIRECTORIES
        if (dist / name).exists() and not (dist / name).is_dir()
    )
    if not (dist / "index.html").is_file():
        errors.append("dist/index.html is missing")

    metadata_path = dist / "metadata.json"
    if not metadata_path.is_file():
        errors.append("dist/metadata.json is missing")
    else:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"dist/metadata.json is not valid JSON: {exc}")
        else:
            for field in ("title", "description"):
                value = metadata.get(field) if isinstance(metadata, dict) else None
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"metadata.{field} must be a nonempty string")

    return {"valid": not errors, "errors": errors, "checked": checked}
