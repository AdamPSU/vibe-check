"""Parse the small metadata contract returned by the game maker."""

from __future__ import annotations

import re
from dataclasses import dataclass


class MetadataError(ValueError):
    """Raised when a maker response does not contain valid catalog metadata."""


@dataclass(frozen=True, slots=True)
class GameMetadata:
    title: str
    description: str


def parse_game_metadata(response: str) -> GameMetadata:
    title_match = re.search(r"(?mi)^\s*TITLE:\s*(.+?)\s*$", response)
    description_match = re.search(r"(?mi)^\s*DESCRIPTION:\s*(.+?)\s*$", response)

    if not title_match or not title_match.group(1).strip():
        raise MetadataError("maker response is missing TITLE:")
    if not description_match or not description_match.group(1).strip():
        raise MetadataError("maker response is missing DESCRIPTION:")

    title = title_match.group(1).strip()
    description = description_match.group(1).strip()
    if len(title) > 120:
        raise MetadataError("title must be 120 characters or fewer")
    if len(description) > 280:
        raise MetadataError("description must be 280 characters or fewer")
    return GameMetadata(title=title, description=description)
