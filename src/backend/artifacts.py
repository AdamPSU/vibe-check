"""Static build validation for generated browser games."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


MAX_TOTAL_BYTES = 5_000_000


@dataclass(slots=True)
class ArtifactReport:
    ok: bool
    root: str
    total_bytes: int = 0
    sha256: str = ""
    missing_files: list[str] = field(default_factory=list)
    external_resources: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return f"artifact valid ({self.total_bytes} bytes, sha256={self.sha256[:12]})"
        problems = self.errors + [f"missing: {item}" for item in self.missing_files]
        problems += [f"external: {item}" for item in self.external_resources]
        return "; ".join(problems) or "artifact validation failed"


class _ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.resources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for name in ("src", "href"):
            value = attributes.get(name)
            if value:
                self.resources.append(value)


def _is_external(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(parsed.scheme or parsed.netloc) and parsed.scheme not in {"data", "blob"}


def validate_build(dist_dir: Path) -> ArtifactReport:
    dist_dir = dist_dir.resolve()
    report = ArtifactReport(ok=False, root=str(dist_dir))
    index = dist_dir / "index.html"
    if not index.is_file():
        report.errors.append("dist/index.html does not exist")
        return report

    all_files = [path for path in dist_dir.rglob("*") if path.is_file()]
    if any(path.is_symlink() for path in all_files):
        report.errors.append("generated build contains symlinks")

    report.total_bytes = sum(path.stat().st_size for path in all_files)
    if report.total_bytes > MAX_TOTAL_BYTES:
        report.errors.append(
            f"generated build is {report.total_bytes} bytes; limit is {MAX_TOTAL_BYTES}"
        )

    digest = hashlib.sha256()
    for path in sorted(all_files):
        digest.update(path.relative_to(dist_dir).as_posix().encode())
        digest.update(path.read_bytes())
    report.sha256 = digest.hexdigest()

    parser = _ResourceParser()
    try:
        parser.feed(index.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        report.errors.append(f"index.html is not UTF-8: {exc}")
        return report

    for resource in parser.resources:
        if resource.startswith(("#", "data:", "blob:")):
            continue
        if _is_external(resource):
            report.external_resources.append(resource)
            continue
        relative = urlsplit(resource).path.lstrip("/")
        target = (dist_dir / relative).resolve()
        try:
            target.relative_to(dist_dir)
        except ValueError:
            report.errors.append(f"resource escapes dist/: {resource}")
            continue
        if not target.is_file():
            report.missing_files.append(relative)

    report.ok = not (
        report.errors or report.missing_files or report.external_resources
    )
    return report
