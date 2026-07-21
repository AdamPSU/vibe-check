"""Local object-storage adapter used by development and tests."""

from __future__ import annotations

import shutil
from pathlib import Path


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        path = Path(key)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe object key: {key}")
        target = (self.root / path).resolve()
        target.relative_to(self.root)
        return target

    def put_tree(self, source: Path, key: str) -> str:
        source = source.resolve()
        if not source.is_dir():
            raise ValueError(f"source tree does not exist: {source}")
        if any(path.is_symlink() for path in source.rglob("*")):
            raise ValueError(f"source tree contains a symlink: {source}")
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        return Path(key).as_posix()
